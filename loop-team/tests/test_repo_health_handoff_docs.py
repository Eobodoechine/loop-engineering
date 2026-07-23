"""Doc regressions for repo-health Coder handoff marker wording.

Run with:
    python3 -m pytest loop-team/tests/test_repo_health_handoff_docs.py -q
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = {
    "orchestrator": ROOT / "loop-team" / "orchestrator.md",
    "team_relations": ROOT / "loop-team" / "TEAM_RELATIONS.md",
    "codex_claude": ROOT / "loop-team" / "CODEX_CLAUDE_TEAM.md",
}

CLASSIFICATION_MARKER = "REPO_HEALTH_CLASSIFICATION="
REPO_MARKER = "REPO_HEALTH_REPO="
ENUM_VALUES = ("new-capability", "continuing-phase", "hardening-bugfix")


def _read(name):
    return DOCS[name].read_text(encoding="utf-8")


def test_all_handoff_docs_document_required_marker_pair():
    for name, path in DOCS.items():
        text = path.read_text(encoding="utf-8")
        assert CLASSIFICATION_MARKER in text, "%s missing classification marker" % name
        assert REPO_MARKER in text, "%s missing repo marker" % name


def test_classification_enum_is_documented_with_marker_context():
    for name, path in DOCS.items():
        text = path.read_text(encoding="utf-8")
        marker_index = text.find(CLASSIFICATION_MARKER)
        assert marker_index != -1, "%s missing classification marker" % name
        context = text[max(0, marker_index - 200):marker_index + 700]
        for value in ENUM_VALUES:
            assert value in context, "%s missing enum value %s near marker" % (name, value)


def test_orchestrator_no_longer_presents_plain_english_as_machine_shape():
    text = _read("orchestrator")
    assert (
        'in this exact shape: `"this dispatch is: new-capability | continuing-phase |'
        not in text
    )
    assert "not accepted by the live guard" in text
    assert "required syntax is `key=value`" in text.lower()


def test_colon_marker_syntax_is_not_documented_as_valid():
    for name, path in DOCS.items():
        text = path.read_text(encoding="utf-8")
        assert "REPO_HEALTH_CLASSIFICATION:" not in text, (
            "%s documents invalid classification colon syntax literally" % name
        )
        assert "REPO_HEALTH_REPO:" not in text, (
            "%s documents invalid repo colon syntax literally" % name
        )
        assert "colon-separated marker syntax" in text.lower() or name == "team_relations"


def test_codex_bridge_documents_native_spawn_agent_message_handoff():
    text = _read("codex_claude")
    assert "spawn_agent" in text
    assert "message" in text
    marker_index = text.find(CLASSIFICATION_MARKER)
    repo_index = text.find(REPO_MARKER, marker_index)
    spawn_index = text.find("spawn_agent")
    message_index = text.find("message")
    assert -1 not in (marker_index, repo_index, spawn_index, message_index)
    assert marker_index < repo_index
