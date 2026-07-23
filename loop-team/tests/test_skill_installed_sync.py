"""AC4 + AC5 (spec: 2026-07-08_skill-template-drift-and-codex-followup):

Structural regression coverage for the SKILL.md/template drift class. The
canonical template (skills/loop-team.SKILL.template.md) declares a STEP 0
live-read file list; the two installed copies
(~/.claude/skills/loop-team/SKILL.md and ~/.agents/skills/loop-team/SKILL.md)
are hand-maintained outside this git repo and can silently drift from it and
from each other. Nothing currently checks either direction. Both tests here
are local-development regression guards, not CI-portable contracts: on a
machine (or CI runner) that has neither installed copy, they SKIP rather than
fail, per the spec's AC5 instruction.
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(REPO, "skills", "loop-team.SKILL.template.md")

INSTALLED_PATHS = [
    os.path.expanduser("~/.claude/skills/loop-team/SKILL.md"),
    os.path.expanduser("~/.agents/skills/loop-team/SKILL.md"),
]


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _missing_installed_paths():
    return [p for p in INSTALLED_PATHS if not os.path.exists(p)]


def _template_step0_basenames(template_text):
    """Return the sorted set of basenames referenced as `<BASE_DIR>/...` file
    reads inside the template's STEP 0 section only (its live-read list),
    e.g. {'orchestrator.md', 'TEAM_RELATIONS.md', 'fix_plan.md',
    'stall_detector.py', 'learnings.md'}."""
    section_match = re.search(r"\*\*STEP 0\b.*?(?=\*\*STEP \d|\Z)", template_text, re.DOTALL)
    section = section_match.group(0) if section_match else template_text
    refs = re.findall(r"<BASE_DIR>/([^`\s*]+)", section)
    return sorted({os.path.basename(ref.rstrip("`")) for ref in refs})


class InstalledCopiesByteIdentical(unittest.TestCase):
    """AC4 — the two installed SKILL.md copies must remain byte-identical to
    each other (their current, pre-fix state), verified by a test rather than
    eyeballed diffs."""

    def test_installed_copies_are_byte_identical(self):
        missing = _missing_installed_paths()
        if missing:
            raise unittest.SkipTest(
                "installed SKILL.md copy not present on this machine, "
                "skipping byte-identical check: %s" % missing
            )
        claude_bytes = open(INSTALLED_PATHS[0], "rb").read()
        agents_bytes = open(INSTALLED_PATHS[1], "rb").read()
        self.assertEqual(
            claude_bytes,
            agents_bytes,
            "installed SKILL.md copies have diverged byte-for-byte: %s vs %s"
            % tuple(INSTALLED_PATHS),
        )


class InstalledCopiesReferenceTemplateBasenames(unittest.TestCase):
    """AC5 — every basename the template's STEP 0 requires as a live-read
    (matched on basename, not full path, since installed copies may resolve
    <BASE_DIR> to an absolute path) must appear somewhere in BOTH installed
    SKILL.md files. This is the regression guard for exactly the drift class
    this spec fixes: the template names a required read
    (TEAM_RELATIONS.md, learnings.md) that an installed copy silently omits."""

    def test_installed_copies_cover_every_template_step0_basename(self):
        missing = _missing_installed_paths()
        if missing:
            raise unittest.SkipTest(
                "installed SKILL.md copy not present on this machine, "
                "skipping basename-coverage check: %s" % missing
            )
        template_text = _read_text(TEMPLATE)
        basenames = _template_step0_basenames(template_text)
        self.assertTrue(
            basenames,
            "template STEP 0 section lists no <BASE_DIR> file references "
            "-- regex likely stale against the template's current text",
        )
        installed_texts = {path: _read_text(path) for path in INSTALLED_PATHS}
        for basename in basenames:
            for path, text in installed_texts.items():
                self.assertIn(
                    basename,
                    text,
                    "installed copy %s does not reference required file "
                    "%r from the template's STEP 0 live-read list" % (path, basename),
                )


if __name__ == "__main__":
    unittest.main()
