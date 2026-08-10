#!/usr/bin/env python3
"""Assert that an exact set of GitHub Actions jobs all succeeded.

Canonical implementation of the `project-required-ci` / `summarize`
aggregation described in MERGE_GATE_SPEC.md sections 2 and 3.

Environment:
  NEEDS_JSON  the `${{ toJSON(needs) }}` context, a JSON object of
              {job_id: {"result": ..., "outputs": {...}}}
  EXPECTED    whitespace-separated job ids that MUST each be present and
              successful. Maintained by hand alongside the workflow's
              `needs:` list.

Exit status 0 only when the job set equals EXPECTED and every result is
exactly "success". Everything else exits 1:

  failure / cancelled / skipped  -> a dependency did not pass
  missing                        -> a job was renamed or deleted and
                                    silently vanished from `needs`
  unexpected                     -> a job was added to `needs` without
                                    being added to EXPECTED

GitHub reports a timed-out job as "failure", so the != "success" test
covers timeouts without a separate case.
"""

from __future__ import annotations

import json
import os
import sys

SUCCESS = "success"


def evaluate(needs: dict, expected) -> tuple[bool, list[str]]:
    """Return (ok, problems). Pure function so it is directly testable."""
    expected_set = set(expected)
    actual_set = set(needs)

    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    not_success = {
        job: (needs[job] or {}).get("result")
        for job in sorted(actual_set & expected_set)
        if (needs[job] or {}).get("result") != SUCCESS
    }

    problems: list[str] = []
    if missing:
        problems.append(
            f"required jobs absent from needs (renamed or deleted?): {missing}"
        )
    if unexpected:
        problems.append(
            f"jobs in needs but not in EXPECTED (update EXPECTED): {unexpected}"
        )
    if not_success:
        problems.append(f"required jobs not successful: {not_success}")

    return (not problems), problems


def main(argv=None) -> int:
    raw_needs = os.environ.get("NEEDS_JSON", "").strip()
    raw_expected = os.environ.get("EXPECTED", "").strip()

    if not raw_expected:
        print("::error::EXPECTED is empty; refusing to pass a gate with no required jobs")
        return 1

    # An unset or malformed needs context must fail closed, never pass.
    try:
        needs = json.loads(raw_needs) if raw_needs else {}
    except json.JSONDecodeError as exc:
        print(f"::error::NEEDS_JSON is not valid JSON: {exc}")
        return 1
    if not isinstance(needs, dict):
        print("::error::NEEDS_JSON must be a JSON object")
        return 1

    ok, problems = evaluate(needs, raw_expected.split())
    for problem in problems:
        print(f"::error::{problem}")
    if ok:
        print(f"all {len(needs)} required jobs succeeded")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
