"""
Core data models for Mosaic.
"""
from dataclasses import dataclass
from typing import List, Optional

# Labels stored in DB / used by the scraper.
COMMENT_TYPE_REVIEW_COMMENT = "review_comment"  # inline diff review comment
COMMENT_TYPE_ISSUE_COMMENT = "issue_comment"  # PR conversation / issue thread
COMMENT_TYPE_REVIEW = "review"  # review summary (approve / request changes)


@dataclass
class Comment_Structure:
    comment_id: Optional[int]
    comment_type: str
    comment_body: Optional[str]
    diff_hunk: Optional[str]  # Code snippet (review_comment only)
    file_path: Optional[str]  # File path (review_comment only)
    author: Optional[str]
    review_state: Optional[str] = None  # APPROVED / CHANGES_REQUESTED / etc.


# Backwards-compatible alias
Review_Comment_Structure = Comment_Structure


@dataclass
class PR_Structure:
    number: int
    title: str
    state: str
    description: Optional[str]
    comments: List[Comment_Structure]
