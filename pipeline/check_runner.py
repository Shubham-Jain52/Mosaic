"""Orchestrate mosaic check: trivial guard → parse → retrieve → analyze."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from ai.analyzer import (
    BaseAnalyzer,
    Feedback,
    HunkAnalysisInput,
    OpenAICompatibleAnalyzer,
)
from ai.chat import OpenAICompatibleChat
from ai.embeddings import Embedder
from core.config import EmbeddingSettings
from core.diff_parser import DiffHunk, is_trivial_diff, parse_unified_diff
from pipeline.retriever import DEFAULT_MAX_DISTANCE, query_similar_comments

DEFAULT_BATCH_SIZE = 5
DEFAULT_RATE_LIMIT_DELAY_S = 0.2


@dataclass
class CheckResult:
    trivial: bool
    feedback: List[Feedback] = field(default_factory=list)
    llm_call_count: int = 0
    hunk_count: int = 0
    hunks_without_history: int = 0
    messages: List[str] = field(default_factory=list)


def _chunked(items: Sequence[HunkAnalysisInput], size: int) -> List[List[HunkAnalysisInput]]:
    n = max(1, int(size))
    return [list(items[i : i + n]) for i in range(0, len(items), n)]


def run_check(
    diff_text: str,
    *,
    top_k: int = 5,
    max_distance: float = DEFAULT_MAX_DISTANCE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rate_limit_delay_s: float = DEFAULT_RATE_LIMIT_DELAY_S,
    analyzer: Optional[BaseAnalyzer] = None,
    embedder: Optional[Embedder] = None,
    settings: Optional[EmbeddingSettings] = None,
) -> CheckResult:
    """
    Run the advisory check pipeline on a unified diff string.

    Skips LLM when the diff is trivial or a hunk has no retrieved history
    (including after the distance gate drops weak neighbors).

    Hunks with history are analyzed in batches (default 5 per LLM call) with a
    short delay between calls to reduce rate-limit pressure.
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

    if analyzer is None:
        worker: BaseAnalyzer = OpenAICompatibleAnalyzer(
            chat=OpenAICompatibleChat(rate_limit_delay_s=rate_limit_delay_s)
        )
    else:
        worker = analyzer

    work: List[HunkAnalysisInput] = []
    without_history = 0

    for hunk in hunks:
        past = query_similar_comments(
            hunk.as_text(),
            top_k=top_k,
            max_distance=max_distance,
            embedder=embedder,
            settings=settings,
        )
        if not past:
            without_history += 1
            continue
        work.append(
            HunkAnalysisInput(
                diff_hunk=hunk.as_text(),
                past_comments=past,
                file_path=hunk.file_path,
            )
        )

    all_feedback: List[Feedback] = []
    llm_calls = 0
    for batch in _chunked(work, batch_size):
        findings = worker.check_batch(batch)
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
