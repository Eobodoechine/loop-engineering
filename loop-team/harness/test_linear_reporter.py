#!/usr/bin/env python3
"""Tests for linear_reporter.py"""
from unittest.mock import MagicMock, patch
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(__file__))
import linear_reporter


def _make_mock_requests(issue_id="ISS-1", title="title", url="https://linear.app/i/1"):
    """Return a mock requests module whose .post returns a successful Linear response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "issueCreate": {
                "success": True,
                "issue": {"id": issue_id, "title": title, "url": url},
            }
        }
    }
    mock_resp.raise_for_status = MagicMock()
    mock_requests = MagicMock()
    mock_requests.post.return_value = mock_resp
    return mock_requests


class TestCreateLinearIssue:

    def test_sends_correct_mutation_when_configured(self, monkeypatch):
        """AC1: sends a request and returns the issue dict when env vars set."""
        monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test123")
        monkeypatch.setenv("LINEAR_TEAM_ID", "team-uuid-abc")
        mock_requests = _make_mock_requests()
        monkeypatch.setattr(linear_reporter, "requests", mock_requests)
        result = linear_reporter.create_linear_issue("title", "desc", priority=3)
        assert result["id"] == "ISS-1"

    def test_request_payload_fields(self, monkeypatch):
        """AC1b: correct teamId and title are sent in the GraphQL payload."""
        monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test123")
        monkeypatch.setenv("LINEAR_TEAM_ID", "team-uuid-abc")
        mock_requests = _make_mock_requests()
        monkeypatch.setattr(linear_reporter, "requests", mock_requests)
        linear_reporter.create_linear_issue("title", "desc", priority=3)
        payload = mock_requests.post.call_args[1]["json"]
        assert payload["variables"]["input"]["teamId"] == "team-uuid-abc"
        assert payload["variables"]["input"]["title"] == "title"

    def test_returns_none_when_api_key_missing(self, monkeypatch):
        """AC2: returns None without raising when LINEAR_API_KEY not set."""
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        monkeypatch.setenv("LINEAR_TEAM_ID", "team-uuid-abc")
        result = linear_reporter.create_linear_issue("title", "desc")
        assert result is None

    def test_report_survivor_no_http_without_creds(self, monkeypatch):
        """AC3: report_survivor makes no HTTP call when env vars absent."""
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        monkeypatch.delenv("LINEAR_TEAM_ID", raising=False)
        mock_requests = MagicMock()
        monkeypatch.setattr(linear_reporter, "requests", mock_requests)
        result = linear_reporter.report_survivor(
            "utils.py", 42, "replace > with >=", "test output here"
        )
        assert result is None
        mock_requests.post.assert_not_called()
