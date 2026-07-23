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
import uuid

TIMEOUT = 600  # seconds
CANONICAL_LOOP_ROOT = "<HOME>/Claude/loop"
CANONICAL_MISSION_CONTROL_ROOT = (
    "<HOME>/Claude/Projects/mission-control"
)


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
            _confcutdir = "--confcutdir=%s" % os.path.abspath(project)
            argv = [py_runner, "-q", _confcutdir] if py_runner else \
                [sys.executable, "-m", "pytest", "-q", _confcutdir]
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


_TYPE_CHECK_BASELINE_FILENAME = ".loop_type_check_baseline.json"


def _resolve_tsc_binary(project):
    """Find a real tsc binary without going through bare `npx tsc`, which
    collides with an unrelated, abandoned npm package literally named `tsc`
    (confirmed live, 2026-07-08: `npx --no-install tsc` in a project that
    declares `typescript` but hasn't installed it exits 1 -- NOT 127 -- with
    npm error ... canceled due to missing packages ... ["tsc@2.0.4"]).

    Resolution order, cheapest/most-specific first:
      1. <project>/node_modules/.bin/tsc -- direct project install.
      2. Walk parent directories (npm/yarn/pnpm workspace hoisting) for
         node_modules/.bin/tsc.
      3. `npx --no-install --package typescript tsc` -- pins the package
         name to avoid the tsc@2.0.4 collision; still exits non-zero with
         the same "canceled due to missing packages" text if typescript
         truly isn't installed/cached anywhere npx can see -- treated as a
         toolchain-unresolvable forced fail by the caller, not a type error.
      4. None resolve -> caller returns a distinct, honest forced-fail
         message; never folded into the same code path as a real tsc error.
    """
    candidate = os.path.join(project, "node_modules", ".bin", "tsc")
    if os.path.isfile(candidate):
        return [candidate]
    d = project
    for _ in range(6):  # bounded walk -- workspace roots are shallow
        parent = os.path.dirname(d)
        if not parent or parent == d:
            break
        d = parent
        candidate = os.path.join(d, "node_modules", ".bin", "tsc")
        if os.path.isfile(candidate):
            return [candidate]
    return ["npx", "--no-install", "--package", "typescript", "tsc"]


def has_typescript_project(project):
    """True only when BOTH a root tsconfig.json exists AND package.json
    declares `typescript` as a dependency (either bucket) -- mirrors
    detect_node_runner's own dependency-declaration gate, not just file
    presence. tsconfig.json missing entirely, or package.json missing
    entirely, or package.json present without a `typescript` dependency
    declared, all return False (a silent routing skip) rather than raising
    -- this is a routing predicate, not a forced-fail check.
    """
    tsconfig_path = os.path.join(project, "tsconfig.json")
    if not os.path.isfile(tsconfig_path):
        return False
    pkg = _load_package_json(project)
    if pkg is None:
        return False
    deps = {}
    deps.update(pkg.get("dependencies") or {})
    deps.update(pkg.get("devDependencies") or {})
    return "typescript" in deps


_TSC_ERROR_RE = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\): error (?P<code>TS\d+):",
    re.MULTILINE,
)


def _parse_tsc_errors(combined_output):
    """Parse `tsc --noEmit` output into a set of (file, code) fingerprints.

    Fingerprint shape is (relative_file_path, ts_error_code) ONLY --
    deliberately excludes line/column and message text: line numbers shift
    as unrelated code in the same file changes across micro-steps, so a
    line-sensitive fingerprint would manufacture a false "new" error on
    every step even when the underlying defect is unchanged. Matches tsc's
    `file(line,col): error TSXXXX: message` line format; any line that
    doesn't match that shape (npm warnings, banner text, "Found N errors"
    summaries) is safely ignored, never raises.
    """
    if not combined_output:
        return set()
    errors = set()
    for m in _TSC_ERROR_RE.finditer(combined_output):
        errors.add((m.group("file"), m.group("code")))
    return errors


def _load_type_check_baseline(project):
    """Load (or self-bootstrap) the persisted tsc error baseline.

    Self-bootstrapping: if <project>/.loop_type_check_baseline.json does
    not exist yet, this is the first checkpoint for the slice -- compute
    the CURRENT tsc error set via the same invocation _type_check_gate
    itself uses (_resolve_tsc_binary + `--noEmit -p tsconfig.json`, parsed
    by _parse_tsc_errors), persist it to the baseline file, and return it.
    This makes the first checkpoint of a slice always pass with zero new
    errors, with no separate "capture baseline" step.

    An EXISTING baseline file is loaded verbatim and never re-derived. A
    corrupted (invalid JSON) or wrong-shape (not a list of [file, code]
    pairs) baseline file raises ValueError with a message that clearly
    identifies the baseline file as the problem -- callers (namely
    _type_check_gate) must catch this and fold it into the standard
    (dict, error) forced-fail contract, never let it escape uncaught.

    Returns a set of (file, code) 2-tuples.
    """
    baseline_path = os.path.join(project, _TYPE_CHECK_BASELINE_FILENAME)
    if not os.path.isfile(baseline_path):
        argv = _resolve_tsc_binary(project) + [
            "--noEmit", "-p", os.path.join(project, "tsconfig.json"),
        ]
        _code, out, err = run(argv, project, timeout=TIMEOUT)
        current = _parse_tsc_errors((out + "\n" + err).strip())
        with open(baseline_path, "w") as f:
            json.dump(sorted(current), f)
        return current

    try:
        with open(baseline_path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(
            "corrupted %s (%s) -- type-check baseline load failed"
            % (_TYPE_CHECK_BASELINE_FILENAME, e)
        )

    valid_shape = (
        isinstance(data, list) and
        all(isinstance(pair, list) and len(pair) == 2 and
            all(isinstance(x, str) for x in pair)
            for pair in data)
    )
    if not valid_shape:
        raise ValueError(
            "malformed %s: expected a JSON list of [file, code] pairs -- "
            "type-check baseline load failed" % _TYPE_CHECK_BASELINE_FILENAME
        )

    return set(tuple(pair) for pair in data)


def _type_check_gate(project):
    """Additive, BASELINE-SCOPED type-check gate. (dict, error) contract,
    mirroring _smoke_gate's shape.

    Inert (ran=False, passed=True, new_errors=[]) when has_typescript_project
    is False -- no behavior change for non-TypeScript projects.

    Otherwise runs tsc via _resolve_tsc_binary, and:
      - if the toolchain itself is unresolvable (npx "canceled due to
        missing packages", or an exit code / output shape that isn't a
        recognizable clean-run or real-type-error run), returns a distinct
        forced fail -- never misreported as "your code is wrong."
      - otherwise diffs the CURRENT tsc error fingerprints against the
        persisted baseline (_load_type_check_baseline) and fails ONLY on
        fingerprints absent from that baseline (genuinely NEW errors this
        checkpoint introduced) -- pre-existing errors at baseline time are
        never re-flagged as new.
      - a corrupted baseline file is caught and converted into the same
        (dict, error) forced-fail contract, never left to crash the caller.
    """
    if not has_typescript_project(project):
        return {"ran": False, "passed": True, "output": "", "new_errors": []}, None

    argv = _resolve_tsc_binary(project) + [
        "--noEmit", "-p", os.path.join(project, "tsconfig.json"),
    ]
    code, out, err = run(argv, project, timeout=TIMEOUT)
    combined = (out + "\n" + err).strip()

    if "canceled due to missing packages" in combined or (
            code not in (0, 1, 2) or ("error TS" not in combined and code != 0)):
        # Toolchain genuinely unresolvable -- distinct from a real type
        # error; never misreport a missing install as "your code is wrong."
        return ({"ran": False, "passed": False, "output": combined[-2000:]},
                "package.json declares typescript but no tsc binary could be "
                "resolved (checked project + parent node_modules/.bin, then "
                "npx --package typescript) -- type-check gate forced fail, "
                "not a type error")

    current_errors = _parse_tsc_errors(combined)
    try:
        baseline_errors = _load_type_check_baseline(project)
    except Exception as e:
        return ({"ran": False, "passed": False, "output": combined[-2000:]},
                "corrupted type-check baseline: %s -- type-check gate "
                "forced fail" % e)
    new_errors = sorted(current_errors - baseline_errors)

    return ({"ran": True, "passed": len(new_errors) == 0,
             "new_errors": new_errors, "output": combined[-8000:]}, None)


def _publish_canonical_loop_result(project, output, passed):
    """Synchronously publish the canonical harness result through Mission Control."""
    if os.path.realpath(project) != CANONICAL_LOOP_ROOT:
        return 0

    root = pathlib.Path(
        os.environ.get("MISSION_CONTROL_ROOT", CANONICAL_MISSION_CONTROL_ROOT)
    ).resolve()
    evidence_dir = root / "control-plane" / "harness-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / ("loop-engineering-{}.json".format(uuid.uuid4().hex))
    evidence_path.write_bytes(output.encode("utf-8"))

    bridge = root / "loop-team" / "harness" / "publish_project_completion.py"
    if not bridge.is_file():
        bridge = pathlib.Path(CANONICAL_MISSION_CONTROL_ROOT) / "loop-team" / "harness" / "publish_project_completion.py"

    command = [
        sys.executable,
        str(bridge),
        "--producer",
        "loop-engineering",
        "--outcome",
        "harness_passed" if passed else "harness_failed",
        "--root",
        str(root),
        "--repo",
        CANONICAL_LOOP_ROOT,
        "--evidence-file",
        str(evidence_path),
    ]
    if root != pathlib.Path(CANONICAL_MISSION_CONTROL_ROOT):
        command.append("--fixture-event")
    published = subprocess.run(command, text=True, capture_output=True)
    if published.returncode:
        detail = (published.stderr or published.stdout).strip()
        print(
            "Mission Control publisher rejected Loop harness completion{}".format(
                ": " + detail if detail else ""
            ),
            file=sys.stderr,
        )
        return published.returncode
    return 0


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
    type_check, type_check_error = _type_check_gate(project)
    result["type_check"] = type_check  # additive; existing contract keys untouched
    if type_check_error is not None:
        result["passed"] = False
        result["summary"] = ("%s | TYPE-CHECK GATE FORCED FAIL: %s"
                             % (result.get("summary") or "", type_check_error))
    elif type_check["ran"] and not type_check["passed"]:
        result["passed"] = False
        result["summary"] = ("%s | type-check gate FAILED (%d new tsc error(s) vs baseline)"
                             % (result.get("summary") or "", len(type_check["new_errors"])))
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
    output = json.dumps(result, indent=2) + "\n"
    publish_code = _publish_canonical_loop_result(project, output, result["passed"])
    sys.stdout.write(output)
    sys.exit(0 if result["passed"] and not publish_code else 1)


if __name__ == "__main__":
    main()
