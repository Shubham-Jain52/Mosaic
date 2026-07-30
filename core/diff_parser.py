"""Parse unified diffs into hunks and detect trivial / empty patches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class DiffHunk:
    file_path: str
    header: str
    body: str

    def as_text(self) -> str:
        parts = []
        if self.file_path:
            parts.append(f"file: {self.file_path}")
        if self.header:
            parts.append(self.header)
        if self.body:
            parts.append(self.body)
        return "\n".join(parts)


def _strip_path_prefix(path: str) -> str:
    raw = (path or "").strip()
    if raw.startswith("a/") or raw.startswith("b/"):
        return raw[2:]
    return raw


def _content_change_lines(text: str) -> List[str]:
    """Return +/- lines that are real content (not file headers)."""
    changes: List[str] = []
    for line in text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+") or line.startswith("-"):
            # Ignore pure +/- markers with only whitespace after
            payload = line[1:]
            if payload.strip():
                changes.append(line)
    return changes


def is_trivial_diff(text: str) -> bool:
    """
    True when the diff is empty, whitespace-only, or has no real +/- content.

    Factual guard — not an LLM judgment.
    """
    if not (text or "").strip():
        return True
    return len(_content_change_lines(text)) == 0


def parse_unified_diff(text: str) -> List[DiffHunk]:
    """
    Split a unified diff into per-file hunks.

    Handles standard `diff --git` / `@@` patches from `git diff`.
    """
    if not (text or "").strip():
        return []

    lines = text.splitlines()
    hunks: List[DiffHunk] = []
    current_file = ""
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("diff --git "):
            parts = line.split()
            # diff --git a/path b/path
            if len(parts) >= 4:
                current_file = _strip_path_prefix(parts[3]) or _strip_path_prefix(parts[2])
            i += 1
            continue

        if line.startswith("+++ "):
            path = line[4:].strip()
            if path != "/dev/null":
                current_file = _strip_path_prefix(path.split("\t", 1)[0])
            i += 1
            continue

        if line.startswith("@@"):
            header = line
            body_lines: List[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if (
                    nxt.startswith("@@")
                    or nxt.startswith("diff --git ")
                ):
                    break
                body_lines.append(nxt)
                i += 1
            hunks.append(
                DiffHunk(
                    file_path=current_file or "unknown",
                    header=header,
                    body="\n".join(body_lines),
                )
            )
            continue

        i += 1

    return hunks
