"""Read helpers for loading PR/comment data into the RAG pipeline."""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

from sqlalchemy.orm import joinedload

from .database import PULL_REQUEST, comments_table, session_local


def _comment_to_dict(comment: comments_table, pr: Optional[PULL_REQUEST] = None) -> Dict:
    pr = pr or comment.pr_relationship
    return {
        "comment_id": comment.comment_id,
        "comment_type": comment.comment_type,
        "pr_number": comment.pr_number,
        "comment_body": comment.comment_body,
        "diff_hunk": comment.diff_hunk,
        "file_path": comment.file_path,
        "author": comment.author,
        "review_state": comment.review_state,
        "pr_title": pr.title if pr else None,
        "pr_state": pr.state if pr else None,
    }


def get_all_prs() -> List[Dict]:
    db = session_local()
    try:
        rows = db.query(PULL_REQUEST).order_by(PULL_REQUEST.number).all()
        return [
            {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "description": pr.description,
            }
            for pr in rows
        ]
    finally:
        db.close()


def get_all_comments(comment_type: Optional[str] = None) -> List[Dict]:
    db = session_local()
    try:
        query = db.query(comments_table).options(
            joinedload(comments_table.pr_relationship)
        )
        if comment_type:
            query = query.filter(comments_table.comment_type == comment_type)
        rows = query.order_by(
            comments_table.pr_number,
            comments_table.comment_type,
            comments_table.comment_id,
        ).all()
        return [_comment_to_dict(comment) for comment in rows]
    finally:
        db.close()


def get_comments_for_pr(
    pr_number: int,
    comment_type: Optional[str] = None,
) -> List[Dict]:
    db = session_local()
    try:
        query = (
            db.query(comments_table)
            .options(joinedload(comments_table.pr_relationship))
            .filter(comments_table.pr_number == pr_number)
        )
        if comment_type:
            query = query.filter(comments_table.comment_type == comment_type)
        rows = query.order_by(
            comments_table.comment_type,
            comments_table.comment_id,
        ).all()
        return [_comment_to_dict(comment) for comment in rows]
    finally:
        db.close()


def count_comments_by_type() -> Dict[str, int]:
    db = session_local()
    try:
        rows = db.query(comments_table.comment_type).all()
        return dict(Counter(row[0] for row in rows))
    finally:
        db.close()


def get_comment_corpus(comment_type: Optional[str] = None) -> List[Dict]:
    """
    Flat corpus entries shaped for embedding later.

    Each item has a composite id (`{type}:{id}`), metadata, and a `text` blob.
    """
    corpus: List[Dict] = []
    for comment in get_all_comments(comment_type=comment_type):
        parts = [f"Type: {comment['comment_type']}"]
        if comment.get("review_state"):
            parts.append(f"Review state: {comment['review_state']}")
        if comment.get("file_path"):
            parts.append(f"File: {comment['file_path']}")
        if comment.get("diff_hunk"):
            parts.append(f"Diff:\n{comment['diff_hunk']}")
        if comment.get("comment_body"):
            parts.append(f"Comment:\n{comment['comment_body']}")
        text = "\n\n".join(parts).strip()
        if not text:
            continue
        corpus.append(
            {
                "id": f"{comment['comment_type']}:{comment['comment_id']}",
                "comment_type": comment["comment_type"],
                "pr_number": comment["pr_number"],
                "file_path": comment["file_path"],
                "author": comment["author"],
                "review_state": comment.get("review_state"),
                "pr_title": comment.get("pr_title"),
                "text": text,
            }
        )
    return corpus
