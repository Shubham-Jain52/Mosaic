"""GitHub-specific scraper for pull requests and labeled comment kinds."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, List, Optional

from requests import Response, get

from core.config import get_github_headers, get_repo
from core.models import (
    COMMENT_TYPE_ISSUE_COMMENT,
    COMMENT_TYPE_REVIEW,
    COMMENT_TYPE_REVIEW_COMMENT,
    Comment_Structure,
    PR_Structure,
)


class GitHubAPIError(RuntimeError):
    """Raised when the GitHub API returns a non-success status."""


def _handle_rate_limit(response: Response) -> None:
    if response.status_code != 403:
        return
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining not in {"0", 0}:
        return
    reset = response.headers.get("X-RateLimit-Reset")
    if reset:
        reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc).isoformat()
        raise GitHubAPIError(
            f"GitHub API rate limit exceeded. Resets at {reset_at} UTC."
        )
    raise GitHubAPIError("GitHub API rate limit exceeded.")


def _request(url: str) -> Response:
    response = get(url, headers=get_github_headers(), timeout=60)
    _handle_rate_limit(response)
    return response


def _paginate(
    url_for_page: Callable[[int], str],
    *,
    error_label: str,
) -> List[dict]:
    page = 1
    items: List[dict] = []
    while True:
        response = _request(url_for_page(page))
        if response.status_code == 404:
            # PR number may not exist as a pull (or was deleted).
            return items
        if response.status_code != 200:
            print(f"Error fetching {error_label}: {response.status_code}")
            return items

        batch = response.json()
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def fetch_review_comments(pr_number: int, owner: str, repo: str) -> List[Comment_Structure]:
    """Inline diff review comments: GET /pulls/{n}/comments."""
    raw = _paginate(
        lambda page: (
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
            f"?per_page=100&page={page}"
        ),
        error_label=f"PR #{pr_number} review comments",
    )
    comments: List[Comment_Structure] = []
    for comment in raw:
        user = comment.get("user") or {}
        comments.append(
            Comment_Structure(
                comment_id=comment.get("id"),
                comment_type=COMMENT_TYPE_REVIEW_COMMENT,
                comment_body=comment.get("body"),
                diff_hunk=comment.get("diff_hunk"),
                file_path=comment.get("path"),
                author=user.get("login"),
            )
        )
    return comments


def fetch_issue_comments(pr_number: int, owner: str, repo: str) -> List[Comment_Structure]:
    """PR conversation / issue-thread comments: GET /issues/{n}/comments."""
    raw = _paginate(
        lambda page: (
            f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
            f"?per_page=100&page={page}"
        ),
        error_label=f"PR #{pr_number} issue comments",
    )
    comments: List[Comment_Structure] = []
    for comment in raw:
        user = comment.get("user") or {}
        comments.append(
            Comment_Structure(
                comment_id=comment.get("id"),
                comment_type=COMMENT_TYPE_ISSUE_COMMENT,
                comment_body=comment.get("body"),
                diff_hunk=None,
                file_path=None,
                author=user.get("login"),
            )
        )
    return comments


def fetch_reviews(pr_number: int, owner: str, repo: str) -> List[Comment_Structure]:
    """Review summaries (approve / comment / changes requested): GET /pulls/{n}/reviews."""
    raw = _paginate(
        lambda page: (
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
            f"?per_page=100&page={page}"
        ),
        error_label=f"PR #{pr_number} reviews",
    )
    comments: List[Comment_Structure] = []
    for review in raw:
        body = (review.get("body") or "").strip()
        state = review.get("state")
        # Skip empty pending shells with no useful text.
        if not body and state in {None, "PENDING"}:
            continue
        if not body and not state:
            continue
        user = review.get("user") or {}
        comments.append(
            Comment_Structure(
                comment_id=review.get("id"),
                comment_type=COMMENT_TYPE_REVIEW,
                comment_body=body or f"[review {state}]",
                diff_hunk=None,
                file_path=None,
                author=user.get("login"),
                review_state=state,
            )
        )
    return comments


def fetch_all_pr_comments(pr_number: int, owner: str, repo: str) -> List[Comment_Structure]:
    """Collect review comments, conversation comments, and review summaries."""
    return (
        fetch_review_comments(pr_number, owner, repo)
        + fetch_issue_comments(pr_number, owner, repo)
        + fetch_reviews(pr_number, owner, repo)
    )


# Backwards-compatible name used by older call sites / docs
def fetch_PR_comments(pr_number: int, owner: str, repo: str) -> List[Comment_Structure]:
    return fetch_all_pr_comments(pr_number, owner, repo)


def fetch_pull_requests(
    owner: Optional[str] = None,
    repo: Optional[str] = None,
) -> List[PR_Structure]:
    """
    Fetch all pull requests and all labeled comment kinds for a repository.
    Uses REPO_OWNER / REPO_NAME from .env when owner/repo are omitted.
    """
    if owner is None or repo is None:
        configured_owner, configured_repo = get_repo()
        owner = owner or configured_owner
        repo = repo or configured_repo

    page = 1
    all_prs: List[PR_Structure] = []

    while True:
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/pulls"
            f"?state=all&per_page=100&page={page}"
        )
        response = _request(url)

        if response.status_code != 200:
            raise GitHubAPIError(
                f"Error fetching PRs: HTTP {response.status_code} — {response.text[:200]}"
            )

        prs = response.json()
        if not prs:
            if page == 1:
                print("No PRs found")
            break

        for pr_data in prs:
            pr_number = pr_data.get("number")
            all_prs.append(
                PR_Structure(
                    number=pr_number,
                    title=pr_data.get("title"),
                    state=pr_data.get("state"),
                    description=pr_data.get("body"),
                    comments=fetch_all_pr_comments(pr_number, owner, repo),
                )
            )

        print(f"Fetched PR page {page}, total PRs so far: {len(all_prs)}")

        if len(prs) < 100:
            break
        page += 1

    return all_prs
