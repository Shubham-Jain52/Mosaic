"""Resolve a git baseline branch and collect a working-tree diff."""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional, Sequence

DEFAULT_BASE_CANDIDATES: Sequence[str] = (
    "origin/main",
    "main",
    "origin/master",
    "master",
)


class GitDiffError(RuntimeError):
    """Raised when git is unavailable or the baseline cannot be resolved."""


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    if not shutil.which("git"):
        raise GitDiffError(
            "git was not found on PATH. Install git or pipe a diff with --stdin."
        )
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _ref_exists(ref: str) -> bool:
    result = _run_git("rev-parse", "--verify", "--quiet", ref)
    return result.returncode == 0


def resolve_diff_base(explicit: Optional[str] = None) -> str:
    """
    Return a git ref to diff against.

    If ``explicit`` is set, verify it exists. Otherwise try
    origin/main → main → origin/master → master.
    """
    # Ensure we are inside a git work tree
    inside = _run_git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or (inside.stdout or "").strip() != "true":
        raise GitDiffError(
            "Not inside a git repository. Run mosaic check from a git repo, "
            "or pass a unified diff via stdin / --stdin."
        )

    if explicit:
        ref = explicit.strip()
        if not ref:
            raise GitDiffError("Diff base cannot be empty.")
        if not _ref_exists(ref):
            raise GitDiffError(
                f"Git ref '{ref}' was not found. Pass a valid --base or fetch the remote."
            )
        return ref

    for candidate in DEFAULT_BASE_CANDIDATES:
        if _ref_exists(candidate):
            return candidate

    raise GitDiffError(
        "Could not find a baseline branch (tried origin/main, main, "
        "origin/master, master). Pass --base <ref> or pipe a diff with --stdin."
    )


def get_working_diff(base: str) -> str:
    """
    Run ``git diff <base>`` (working tree + index vs baseline tip).

    Returns the unified diff text (may be empty).
    """
    result = _run_git("diff", base)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise GitDiffError(
            f"git diff {base} failed"
            + (f": {err}" if err else ".")
        )
    return result.stdout or ""
