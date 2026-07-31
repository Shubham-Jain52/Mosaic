"""Unit tests for diff parsing, trivial detection, and feedback filtering."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

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

    def test_filter_allowed_prs_intersection(self):
        items = [
            Feedback("ok", "blocking", "a.py", cited_prs=[10, 99]),
            Feedback("bad cite", "suggestion", "a.py", cited_prs=[999]),
            Feedback("mixed", "nit", "a.py", cited_prs=[10, 50]),
        ]
        kept = filter_feedback(
            items,
            require_citations=True,
            allowed_prs={10, 20},
        )
        self.assertEqual(len(kept), 2)
        by_issue = {f.issue: f for f in kept}
        self.assertEqual(by_issue["ok"].cited_prs, [10])
        self.assertEqual(by_issue["mixed"].cited_prs, [10])
        self.assertNotIn("bad cite", by_issue)

    def test_parse_feedback_json(self):
        raw = '[{"issue":"missing guard","severity":"blocking","file_path":"a.py","line_hint":"10","cited_prs":[1,2]}]'
        parsed = parse_feedback_json(raw, default_file_path="a.py")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].severity, "blocking")
        self.assertEqual(parsed[0].cited_prs, [1, 2])

    def test_analyzer_blank_drops_empty_past(self):
        from ai.analyzer import OpenAICompatibleAnalyzer

        findings = OpenAICompatibleAnalyzer(chat=object()).check(  # type: ignore[arg-type]
            "@@ hunk",
            [],
            file_path="a.py",
        )
        self.assertEqual(findings, [])

    def test_analyzer_passes_allowed_prs_to_filter(self):
        from ai.analyzer import CHECK_SYSTEM_PROMPT, OpenAICompatibleAnalyzer
        from unittest.mock import MagicMock

        mock_chat = MagicMock()
        mock_chat.complete.return_value = (
            '[{"issue":"secret","severity":"blocking","file_path":"a.py",'
            '"line_hint":null,"cited_prs":[7,999]}]'
        )
        analyzer = OpenAICompatibleAnalyzer(chat=mock_chat)
        findings = analyzer.check(
            "@@ +api_key",
            [{"pr_number": 7, "text": "do not hardcode keys", "author": "a", "file_path": "a.py"}],
            file_path="a.py",
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].cited_prs, [7])
        system_msg = mock_chat.complete.call_args.args[0][0]["content"]
        self.assertEqual(system_msg, CHECK_SYSTEM_PROMPT)
        self.assertIn("Prefer []", system_msg)

    def test_check_batch_one_llm_call_for_multiple_hunks(self):
        from ai.analyzer import HunkAnalysisInput, OpenAICompatibleAnalyzer
        from unittest.mock import MagicMock

        mock_chat = MagicMock()
        mock_chat.complete.return_value = (
            "["
            '{"issue":"secret","severity":"blocking","file_path":"a.py",'
            '"line_hint":null,"cited_prs":[1],"hunk_index":1},'
            '{"issue":"unused","severity":"nit","file_path":"b.py",'
            '"line_hint":null,"cited_prs":[2],"hunk_index":2}'
            "]"
        )
        analyzer = OpenAICompatibleAnalyzer(chat=mock_chat)
        findings = analyzer.check_batch(
            [
                HunkAnalysisInput(
                    diff_hunk="+api_key",
                    past_comments=[
                        {"pr_number": 1, "text": "no secrets", "author": "a", "file_path": "a.py"}
                    ],
                    file_path="a.py",
                ),
                HunkAnalysisInput(
                    diff_hunk="+flag=True",
                    past_comments=[
                        {"pr_number": 2, "text": "remove unused", "author": "b", "file_path": "b.py"}
                    ],
                    file_path="b.py",
                ),
            ]
        )
        mock_chat.complete.assert_called_once()
        self.assertEqual(len(findings), 2)
        self.assertEqual({f.file_path for f in findings}, {"a.py", "b.py"})


class CheckRunnerBatchTests(unittest.TestCase):
    def test_run_check_batches_hunks(self):
        from core.diff_parser import DiffHunk
        from pipeline import check_runner as cr

        hunks = [
            DiffHunk(file_path="a.py", header="@@ -1 +1 @@", body="+a"),
            DiffHunk(file_path="b.py", header="@@ -1 +1 @@", body="+b"),
            DiffHunk(file_path="c.py", header="@@ -1 +1 @@", body="+c"),
        ]
        mock_analyzer = MagicMock()
        mock_analyzer.check_batch.side_effect = [
            [Feedback("x", "blocking", "a.py", cited_prs=[1])],
            [],
        ]

        with patch.object(cr, "is_trivial_diff", return_value=False), patch.object(
            cr, "parse_unified_diff", return_value=hunks
        ), patch.object(
            cr,
            "query_similar_comments",
            return_value=[{"pr_number": 1, "text": "t", "author": "a", "file_path": "a.py"}],
        ):
            result = cr.run_check(
                "diff",
                batch_size=2,
                rate_limit_delay_s=0,
                analyzer=mock_analyzer,
            )

        # 3 hunks with history, batch_size=2 → 2 LLM calls
        self.assertEqual(result.llm_call_count, 2)
        self.assertEqual(mock_analyzer.check_batch.call_count, 2)
        self.assertEqual(result.hunk_count, 3)
        self.assertEqual(len(result.feedback), 1)


class ChatRateLimitTests(unittest.TestCase):
    def test_retries_on_429_then_succeeds(self):
        from ai.chat import OpenAICompatibleChat, ChatSettings

        mock_client = MagicMock()
        ok = MagicMock()
        ok.choices = [MagicMock(message=MagicMock(content="[]"))]
        mock_client.chat.completions.create.side_effect = [
            RuntimeError("Error code: 429 - rate limit exceeded"),
            ok,
        ]

        with patch("openai.OpenAI", return_value=mock_client), patch(
            "time.sleep"
        ) as mock_sleep:
            chat = OpenAICompatibleChat(
                ChatSettings(api_key="k", model="m"),
                rate_limit_delay_s=0,
                max_retries=3,
            )
            chat._client = mock_client
            out = chat.complete([{"role": "user", "content": "hi"}])

        self.assertEqual(out, "[]")
        self.assertEqual(mock_client.chat.completions.create.call_count, 2)
        mock_sleep.assert_called()


class RetrieverDistanceGateTests(unittest.TestCase):
    def test_drops_hits_above_max_distance(self):
        from pipeline import retriever as ret

        mock_collection = MagicMock()
        mock_collection.count.return_value = 2
        mock_collection.query.return_value = {
            "ids": [["a", "b"]],
            "documents": [["near comment", "far comment"]],
            "metadatas": [
                [
                    {"pr_number": 1, "file_path": "a.py", "author": "x", "comment_type": "review_comment"},
                    {"pr_number": 2, "file_path": "b.py", "author": "y", "comment_type": "review_comment"},
                ]
            ],
            "distances": [[0.4, 1.9]],
        }
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1, 0.2]
        mock_settings = MagicMock()

        with patch.object(
            ret, "_get_collection", return_value=(mock_collection, "c", "/tmp")
        ), patch.object(ret, "get_embedding_settings", return_value=mock_settings), patch.object(
            ret, "get_embedder", return_value=mock_embedder
        ):
            results = ret.query_similar_comments(
                "some hunk",
                top_k=5,
                max_distance=1.2,
                embedder=mock_embedder,
                settings=mock_settings,
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "a")
        self.assertEqual(results[0]["pr_number"], 1)

    def test_keeps_hits_without_distance(self):
        from pipeline import retriever as ret

        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            "ids": [["a"]],
            "documents": [["comment"]],
            "metadatas": [[{"pr_number": 3, "file_path": "", "author": "", "comment_type": ""}]],
            "distances": [[]],
        }
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.0]
        mock_settings = MagicMock()

        with patch.object(
            ret, "_get_collection", return_value=(mock_collection, "c", "/tmp")
        ):
            results = ret.query_similar_comments(
                "hunk",
                max_distance=0.1,
                embedder=mock_embedder,
                settings=mock_settings,
            )
        self.assertEqual(len(results), 1)

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
