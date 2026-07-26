"""
Core data models for Mosaic.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Review_Comment_Structure:
    comment_id: Optional[int]
    comment_body: Optional[str]
    diff_hunk: Optional[str]  # The code snippet
    file_path: Optional[str]  # Which file they commented on
    author: Optional[str]


@dataclass
class PR_Structure:
    number: int
    title: str
    state: str
    description: Optional[str]
    comments: List[Review_Comment_Structure]
