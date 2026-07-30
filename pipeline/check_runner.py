"""Orchestrate mosaic check: trivial guard → parse → retrieve → analyze."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from ai.analyzer import BaseAnalyzer, Feedback, OpenAICompatibleAnalyzer
from ai.embeddings import Embedder
from core.config import EmbeddingSettings
from core.diff_parser import DiffHunk, is_trivial_diff, parse_unified_diff
from pipeline.retriever import query_similar_comments


@dataclass
class CheckResult:
    trivial: bool
    feedback: List[Feedback] = field(default_factory=list)
    llm_call_count: int = 0
    hunk_count: int = 0
    hunks_without_history: int = 0
    messages: List[str] = field(default_factory=list)


def run_check(
    diff_text: str,
    *,
    top_k: int = 5,
    analyzer: Optional[BaseAnalyzer] = None,
    embedder: Optional[Embedder] = None,
    settings: Optional[EmbeddingSettings] = None,
) -> CheckResult:
    """
    Run the advisory check pipeline on a unified diff string.

    Skips LLM when the diff is trivial or a hunk has no retrieved history.
    """
    if is_trivial_diff(diff_text):
        return CheckResult(
            trivial=True,
            messages=["no meaningful changes detected"],
        )

    hunks: Sequence[DiffHunk] = parse_unified_diff(diff_text)
    if not hunks:
        return CheckResult(
            trivial=True,
            messages=["no meaningful changes detected"],
        )

    worker = analyzer or OpenAICompatibleAnalyzer()
    all_feedback: List[Feedback] = []
    llm_calls = 0
    without_history = 0

    for hunk in hunks:
        past = query_similar_comments(
            hunk.as_text(),
            top_k=top_k,
            embedder=embedder,
            settings=settings,
        )
        if not past:
            without_history += 1
            continue

        findings = worker.check(
            hunk.as_text(),
            past,
            file_path=hunk.file_path,
        )
        llm_calls += 1
        all_feedback.extend(findings)

    messages: List[str] = []
    if without_history == len(hunks) and not all_feedback:
        messages.append(
            "not enough relevant history to comment on these changes"
        )
    elif without_history:
        messages.append(
            f"{without_history}/{len(hunks)} hunk(s) had no relevant past comments"
        )

    return CheckResult(
        trivial=False,
        feedback=all_feedback,
        llm_call_count=llm_calls,
        hunk_count=len(hunks),
        hunks_without_history=without_history,
        messages=messages,
    )
