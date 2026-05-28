"""
Core data models for Mosaic.
"""
from dataclasses import dataclass
from typing import List

@dataclass
class Review_Comment_Structure:
    comment_id: int
    comment_body: str
    diff_hunk: str     # The code snippet
    file_path: str     # Which file they commented on
    author: str
@dataclass
class PR_Structure:
    number: int
    title: str
    state : str
    description: str
    comments: List[Review_Comment_Structure]


