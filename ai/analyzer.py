"""Diff analyzer: typed Feedback seam + OpenAI-compatible implementation."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AbstractSet, Any, Dict, List, Literal, Optional, Sequence

from ai.chat import ChatError, OpenAICompatibleChat

Severity = Literal["blocking", "suggestion", "nit"]
_VALID_SEVERITIES = {"blocking", "suggestion", "nit"}

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

CHECK_SYSTEM_PROMPT = (
    "You are Mosaic check: a code-review assistant grounded ONLY in the "
    "provided past review comments from this team's PRs. "
    "Return a JSON array of feedback objects. Each object must have: "
    'issue (string), severity ("blocking"|"suggestion"|"nit"), '
    "file_path (string), line_hint (string|null), cited_prs (array of ints). "
    "Severity rubric: "
    "blocking = correctness or security patterns clearly echoed in the past comments; "
    "suggestion = concrete recurring team guidance that clearly applies to this hunk; "
    "nit = style or naming only when past comments say so. "
    "Every finding MUST cite at least one PR number that appears in the past comments. "
    "Prefer [] when past comments are only loosely related — do not stretch weak matches. "
    "If nothing in the past comments clearly applies, return []. "
    "Do not invent generic best-practice advice. "
    "Output JSON only — no markdown prose."
)


@dataclass
class Feedback:
    issue: str
    severity: Severity
    file_path: str
    line_hint: Optional[str] = None
    cited_prs: List[int] = field(default_factory=list)


def normalize_severity(value: Any) -> Optional[Severity]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _VALID_SEVERITIES:
        return text  # type: ignore[return-value]
    return None


def filter_feedback(
    items: Sequence[Feedback],
    *,
    require_citations: bool,
    allowed_prs: Optional[AbstractSet[int]] = None,
) -> List[Feedback]:
    """
    Pure validation: drop empty issues and uncitable advice when required.

    When ``allowed_prs`` is set, keep a finding only if at least one cited PR
    is in that set, and trim ``cited_prs`` to the intersection.
    """
    out: List[Feedback] = []
    for item in items:
        issue = (item.issue or "").strip()
        if not issue:
            continue
        severity = normalize_severity(item.severity)
        if severity is None:
            continue
        cleaned_cited: List[int] = []
        for n in item.cited_prs or []:
            try:
                cleaned_cited.append(int(n))
            except (TypeError, ValueError):
                continue
        cited = sorted(set(cleaned_cited))
        if allowed_prs is not None:
            cited = [n for n in cited if n in allowed_prs]
        if require_citations and not cited:
            continue
        out.append(
            Feedback(
                issue=issue,
                severity=severity,
                file_path=(item.file_path or "").strip() or "unknown",
                line_hint=(item.line_hint.strip() if item.line_hint else None),
                cited_prs=cited,
            )
        )
    return out


def parse_feedback_json(raw: str, *, default_file_path: str) -> List[Feedback]:
    """Parse model JSON into Feedback objects (no I/O)."""
    text = (raw or "").strip()
    if not text:
        return []

    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON array substring
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            return []
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []

    if isinstance(payload, dict):
        payload = payload.get("feedback") or payload.get("items") or []
    if not isinstance(payload, list):
        return []

    parsed: List[Feedback] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        severity = normalize_severity(row.get("severity"))
        if severity is None:
            continue
        cited_raw = row.get("cited_prs") or []
        if not isinstance(cited_raw, list):
            cited_raw = []
        cited: List[int] = []
        for n in cited_raw:
            try:
                cited.append(int(n))
            except (TypeError, ValueError):
                continue
        line_hint = row.get("line_hint")
        parsed.append(
            Feedback(
                issue=str(row.get("issue") or "").strip(),
                severity=severity,
                file_path=str(row.get("file_path") or default_file_path or "unknown").strip(),
                line_hint=str(line_hint).strip() if line_hint not in (None, "") else None,
                cited_prs=cited,
            )
        )
    return parsed


class BaseAnalyzer(ABC):
    @abstractmethod
    def check(
        self,
        diff_hunk: str,
        past_comments: List[Dict[str, Any]],
        *,
        file_path: str = "unknown",
    ) -> List[Feedback]:
        raise NotImplementedError


class OpenAICompatibleAnalyzer(BaseAnalyzer):
    """
    LLM analyzer for mosaic check.

    Could later support describe/ask via different prompts; v1.0.0 only implements check.
    """

    def __init__(self, chat: Optional[OpenAICompatibleChat] = None):
        self._chat = chat or OpenAICompatibleChat()

    def check(
        self,
        diff_hunk: str,
        past_comments: List[Dict[str, Any]],
        *,
        file_path: str = "unknown",
    ) -> List[Feedback]:
        # Blank-drop: no relevant history → no invented advice
        if not past_comments:
            return []

        allowed_prs: set[int] = set()
        comments_block = []
        for idx, comment in enumerate(past_comments, start=1):
            pr = comment.get("pr_number")
            if pr is not None:
                try:
                    allowed_prs.add(int(pr))
                except (TypeError, ValueError):
                    pass
            pr_label = f"PR #{pr}" if pr is not None else "PR unknown"
            author = comment.get("author") or "unknown"
            path = comment.get("file_path") or ""
            body = (comment.get("text") or "").strip()
            comments_block.append(
                f"[{idx}] {pr_label} author={author} file={path}\n{body}"
            )

        user = (
            f"File under review: {file_path}\n\n"
            f"Diff hunk:\n{diff_hunk}\n\n"
            f"Past review comments:\n" + "\n\n".join(comments_block)
        )

        try:
            raw = self._chat.complete(
                [
                    {"role": "system", "content": CHECK_SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ]
            )
        except ChatError:
            raise

        return filter_feedback(
            parse_feedback_json(raw, default_file_path=file_path),
            require_citations=True,
            allowed_prs=allowed_prs if allowed_prs else None,
        )
