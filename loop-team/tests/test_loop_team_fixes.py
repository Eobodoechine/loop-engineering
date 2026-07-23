"""
Tests for loop-team fix acceptance criteria.

AC1 [BEHAVIORAL]: roles/verifier.md does NOT contain the relative path `python loop-team/harness/verify.py`
AC2 [BEHAVIORAL]: roles/live_smoke.md does NOT contain the relative path `python3 loop-team/harness/live_smoke.py`
AC3 [DOC]: SKILL.md indicates VERIFIER.md is domain-specific (NOT a general build rubric)
AC4 [DOC]: SKILL.md contains the absolute path to stall_detector.py
AC5 [DOC]: SKILL.md qualifies fix_plan.md application by domain

Run with: pytest loop-team/tests/test_loop_team_fixes.py (from repo root)
"""
import os

_LOOP_PUBLIC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERIFIER_MD = os.path.join(_LOOP_PUBLIC, "loop-team/roles/verifier.md")
LIVE_SMOKE_MD = os.path.join(_LOOP_PUBLIC, "loop-team/roles/live_smoke.md")
SKILL_MD = os.path.expanduser("~/.claude/skills/loop-team/SKILL.md")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 [BEHAVIORAL]
# ---------------------------------------------------------------------------

def test_ac1_verifier_md_no_relative_harness_path():
    """
    roles/verifier.md must NOT reference verify.py via the relative path
    `python loop-team/harness/verify.py`.  That path only works when the
    working directory happens to be the repo root; it must have been replaced
    with an absolute path.
    """
    content = _read(VERIFIER_MD)
    assert "python loop-team/harness/verify.py" not in content, (
        "roles/verifier.md still contains the relative path "
        "'python loop-team/harness/verify.py'. "
        "Replace it with the absolute path."
    )


# ---------------------------------------------------------------------------
# AC2 [BEHAVIORAL]
# ---------------------------------------------------------------------------

def test_ac2_live_smoke_md_no_relative_harness_path():
    """
    roles/live_smoke.md must NOT reference live_smoke.py via the relative
    path `python3 loop-team/harness/live_smoke.py`.  It must have been
    replaced with an absolute path.
    """
    content = _read(LIVE_SMOKE_MD)
    assert "python3 loop-team/harness/live_smoke.py" not in content, (
        "roles/live_smoke.md still contains the relative path "
        "'python3 loop-team/harness/live_smoke.py'. "
        "Replace it with the absolute path."
    )


# ---------------------------------------------------------------------------
# AC3 [DOC]
# ---------------------------------------------------------------------------

def test_ac3_skill_md_verifier_described_as_domain_specific():
    """
    SKILL.md must describe VERIFIER.md as domain-specific (career-finder /
    job-listing / rental / similar), NOT as a general build rubric that
    applies to all builds.

    Acceptable signals include any of: "domain-specific", "job-listing",
    "career-finder", "rental", "domain specific", "applies only to",
    "not a general".
    """
    content = _read(SKILL_MD).lower()
    domain_signals = [
        "domain-specific",
        "domain specific",
        "job-listing",
        "job listing",
        "career-finder",
        "career finder",
        "rental",
        "applies only to",
        "not a general",
        "not the general",
    ]
    matched = [sig for sig in domain_signals if sig in content]
    assert matched, (
        "SKILL.md does not describe VERIFIER.md as domain-specific or "
        "limited to career-finder / job-listing / rental builds. "
        f"Expected at least one of: {domain_signals}"
    )


# ---------------------------------------------------------------------------
# AC4 [DOC]
# ---------------------------------------------------------------------------

def test_ac4_skill_md_contains_absolute_stall_detector_path():
    """
    SKILL.md must contain the absolute path to stall_detector.py, either as
    the full expanded path or using the ~ home shorthand.

    Accepted forms:
      <repo_root>/loop-team/harness/stall_detector.py  (absolute, derived from __file__)
      ~/Claude/loop/loop-team/harness/stall_detector.py
    """
    content = _read(SKILL_MD)
    absolute_forms = [
        os.path.join(_LOOP_PUBLIC, "loop-team/harness/stall_detector.py"),
        "~/Claude/loop/loop-team/harness/stall_detector.py",
    ]
    matched = [p for p in absolute_forms if p in content]
    assert matched, (
        "SKILL.md does not contain the absolute path to stall_detector.py. "
        f"Expected one of: {absolute_forms}"
    )


# ---------------------------------------------------------------------------
# AC5 [DOC]
# ---------------------------------------------------------------------------

def test_ac5_skill_md_fix_plan_qualified_by_domain():
    """
    SKILL.md must qualify the application of fix_plan.md so it is not
    blindly applied to every build.  The qualifier must appear within a
    few lines of any mention of fix_plan.md.

    Acceptable qualifier words near fix_plan.md: "relevant", "domain",
    "career-finder", "rentals", "if they're relevant", "applicable",
    "applies to this".
    """
    content = _read(SKILL_MD)

    # Find the region of text around every mention of fix_plan.md
    import re
    qualifier_pattern = re.compile(
        r"relevant|domain|career.finder|rentals?|if they.re relevant|applicable|applies to this",
        re.IGNORECASE,
    )

    # Split into blocks of ~300 chars centred on each fix_plan.md mention
    mentions = [m.start() for m in re.finditer(r"fix_plan\.md", content)]
    assert mentions, "SKILL.md does not mention fix_plan.md at all — cannot verify qualifier."

    window = 300  # characters on each side of the mention
    found_qualifier = False
    for pos in mentions:
        snippet = content[max(0, pos - window): pos + window]
        if qualifier_pattern.search(snippet):
            found_qualifier = True
            break

    assert found_qualifier, (
        "SKILL.md mentions fix_plan.md but does not qualify its application "
        "with a domain-limiting phrase (e.g. 'relevant', 'domain', "
        "'career-finder', 'rentals', 'if they're relevant to this build'). "
        "Add a qualifier so the Coder knows not to apply every open item to "
        "every build."
    )
