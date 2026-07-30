"""Unit tests for diff parsing, trivial detection, and feedback filtering."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai.analyzer import Feedback, filter_feedback, normalize_severity, parse_feedback_json
from core.diff_parser import is_trivial_diff, parse_unified_diff
from core.git_diff import GitDiffError, resolve_diff_base


SAMPLE_DIFF = """\
diff --git a/foo.py b/foo.py
index 111..222 100644
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,4 @@
 def hello():
-    return 1
+    return 2
+    # note
"""


class DiffParserTests(unittest.TestCase):
    def test_trivial_empty(self):
        self.assertTrue(is_trivial_diff(""))
        self.assertTrue(is_trivial_diff("   \n\n"))

    def test_trivial_whitespace_only_changes(self):
        diff = """\
diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-
+
"""
        self.assertTrue(is_trivial_diff(diff))

    def test_non_trivial(self):
        self.assertFalse(is_trivial_diff(SAMPLE_DIFF))

    def test_parse_hunks(self):
        hunks = parse_unified_diff(SAMPLE_DIFF)
        self.assertEqual(len(hunks), 1)
        self.assertEqual(hunks[0].file_path, "foo.py")
        self.assertTrue(hunks[0].header.startswith("@@"))
        self.assertIn("return 2", hunks[0].body)


class AnalyzerPureTests(unittest.TestCase):
    def test_normalize_severity(self):
        self.assertEqual(normalize_severity("BLOCKING"), "blocking")
        self.assertIsNone(normalize_severity("critical"))

    def test_filter_requires_citations(self):
        items = [
            Feedback("x", "nit", "a.py", cited_prs=[]),
            Feedback("y", "suggestion", "a.py", cited_prs=[3]),
        ]
        kept = filter_feedback(items, require_citations=True)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].issue, "y")

    def test_parse_feedback_json(self):
        raw = '[{"issue":"missing guard","severity":"blocking","file_path":"a.py","line_hint":"10","cited_prs":[1,2]}]'
        parsed = parse_feedback_json(raw, default_file_path="a.py")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].severity, "blocking")
        self.assertEqual(parsed[0].cited_prs, [1, 2])


class GitDiffResolveTests(unittest.TestCase):
    @patch("core.git_diff._run_git")
    def test_resolve_picks_first_existing(self, mock_run):
        def fake(*args):
            class R:
                def __init__(self, code, out=""):
                    self.returncode = code
                    self.stdout = out
                    self.stderr = ""

            if args[:2] == ("rev-parse", "--is-inside-work-tree"):
                return R(0, "true\n")
            if args[:3] == ("rev-parse", "--verify", "--quiet"):
                ref = args[3]
                return R(0 if ref == "main" else 1)
            return R(1)

        mock_run.side_effect = fake
        self.assertEqual(resolve_diff_base(None), "main")

    @patch("core.git_diff._run_git")
    def test_not_a_repo(self, mock_run):
        class R:
            returncode = 128
            stdout = ""
            stderr = "fatal"

        mock_run.return_value = R()
        with self.assertRaises(GitDiffError):
            resolve_diff_base(None)


if __name__ == "__main__":
    unittest.main()
