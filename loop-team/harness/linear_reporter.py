#!/usr/bin/env python3
"""
linear_reporter.py — Creates Linear issues from loop test failures.

Silently no-ops if LINEAR_API_KEY or LINEAR_TEAM_ID is not set, or if
`requests` is not installed. Never raises — callers should not fail if
Linear is not configured.

Usage (CLI):
    python3 linear_reporter.py --title "..." --description "..." [--priority 2]

Or import:
    from linear_reporter import report_survivor, report_test_failure
"""
import argparse
import json
import os
import sys

try:
    import requests
except ImportError:
    requests = None

LINEAR_ENDPOINT = "https://api.linear.app/graphql"

_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id title url }
  }
}
"""


def create_linear_issue(title, description, priority=3):
    """Create one Linear issue. Returns issue dict or None if skipped/failed.

    Env vars required:
        LINEAR_API_KEY  — from Linear Settings → Account → Security & access
        LINEAR_TEAM_ID  — from GraphQL { teams { nodes { id name } } } query
    """
    api_key = os.environ.get("LINEAR_API_KEY")
    team_id = os.environ.get("LINEAR_TEAM_ID")
    if not api_key or not team_id or not requests:
        return None
    try:
        resp = requests.post(
            LINEAR_ENDPOINT,
            json={
                "query": _MUTATION,
                "variables": {
                    "input": {
                        "teamId": team_id,
                        "title": title,
                        "description": description,
                        "priority": priority,
                    }
                },
            },
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            return None
        return data["data"]["issueCreate"]["issue"]
    except Exception:
        return None


def report_survivor(file, line, mutation_desc, test_output=""):
    """Format a surviving mutant and create a Linear issue."""
    title = f"Surviving mutant: {file}:{line} ({mutation_desc})"
    description = (
        f"## Surviving Mutant\n\n"
        f"**File:** `{file}`  \n"
        f"**Line:** {line}  \n"
        f"**Mutation:** {mutation_desc}\n\n"
        f"All tests passed against this mutation — add a test that kills it.\n\n"
        + (
            f"### Test output\n```\n{test_output[:2000]}\n```"
            if test_output
            else ""
        )
    )
    return create_linear_issue(title, description, priority=3)


def report_test_failure(test_name, file, line, failure_output=""):
    """Format a test failure and create a Linear issue."""
    title = f"Test failure: {test_name} ({file}:{line})"
    description = (
        f"## Test Failure\n\n"
        f"**Test:** `{test_name}`  \n"
        f"**File:** `{file}`  \n"
        f"**Line:** {line}\n\n"
        + (
            f"### Failure output\n```\n{failure_output[:2000]}\n```"
            if failure_output
            else ""
        )
    )
    return create_linear_issue(title, description, priority=2)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Create a Linear issue from a test failure."
    )
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--priority", type=int, default=3,
                   help="1=Urgent 2=High 3=Medium 4=Low")
    args = p.parse_args()
    issue = create_linear_issue(args.title, args.description, args.priority)
    if issue:
        print(json.dumps(issue))
        sys.exit(0)
    else:
        print("skipped (LINEAR_API_KEY/LINEAR_TEAM_ID not set, or error)", file=sys.stderr)
        sys.exit(0)  # always exit 0 — missing Linear config must not fail the loop
