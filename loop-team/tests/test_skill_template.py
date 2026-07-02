"""AC6: the shipped SKILL template's STEP-0 file list must resolve against the
repo tree (every non-private path exists), so the template cannot drift from the
layout. Private paths are recognized by their 'skip if' marking."""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(REPO, "skills", "loop-team.SKILL.template.md")


class TemplateResolves(unittest.TestCase):
    def test_step0_paths_exist_or_marked_private(self):
        text = open(TEMPLATE, encoding="utf-8").read()
        refs = re.findall(r"`<BASE_DIR>/([^`*]+?)`(.{0,120})", text)
        self.assertTrue(refs, "template lists no <BASE_DIR> paths")
        for rel, trailing in refs:
            full = os.path.join(REPO, rel.strip())
            if os.path.exists(full):
                continue
            self.assertIn("skip if", trailing,
                          "template references missing path %r without a "
                          "'skip if' private marking" % rel)

    def test_template_names_the_gate_arming_file(self):
        text = open(TEMPLATE, encoding="utf-8").read()
        self.assertIn("_target", text)
        self.assertIn("orchestrator.md", text)
