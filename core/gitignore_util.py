"""Ensure Mosaic local artifacts are listed in the project .gitignore."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

# Paths Mosaic writes into a connected project (secrets + regenerable data).
MOSAIC_GITIGNORE_ENTRIES: Sequence[str] = (
    ".env",
    ".mosaic/",
    "mosaic.db",
)

_SECTION_HEADER = "# Mosaic (added by mosaic init)"


def _entry_covered(existing_lines: Sequence[str], entry: str) -> bool:
    """True if entry (or a close variant) already appears in .gitignore."""
    target = entry.strip()
    variants = {
        target,
        target.lstrip("./"),
        target.rstrip("/"),
        f"{target.rstrip('/')}/",
    }
    if target == ".env":
        variants.update({".env", "**/.env", "/.env"})

    for raw in existing_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in variants or stripped.rstrip("/") in variants:
            return True
    return False


def ensure_mosaic_gitignore(gitignore_path: Path = Path(".gitignore")) -> List[str]:
    """
    Append missing Mosaic ignore rules to ``gitignore_path``.

    Creates the file if needed. Returns the list of entries that were added.
    """
    existing_lines: List[str] = []
    if gitignore_path.exists():
        existing_lines = gitignore_path.read_text().splitlines()

    missing = [
        entry
        for entry in MOSAIC_GITIGNORE_ENTRIES
        if not _entry_covered(existing_lines, entry)
    ]
    if not missing:
        return []

    block_lines = [_SECTION_HEADER, *missing]
    block = "\n".join(block_lines) + "\n"

    if not gitignore_path.exists():
        gitignore_path.write_text(block)
        return list(missing)

    text = gitignore_path.read_text()
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        # one blank line before our section when file already has content
        if not text.endswith("\n"):
            text += "\n"
        text += "\n"
    gitignore_path.write_text(text + block)
    return list(missing)
