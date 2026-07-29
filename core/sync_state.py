"""Persist Mosaic sync bookmarks under .mosaic/sync_state.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Set

from .config import MOSAIC_DIR, ensure_mosaic_dirs

SYNC_STATE_PATH = MOSAIC_DIR / "sync_state.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SyncState:
    known_pr_numbers: List[int] = field(default_factory=list)
    indexed_comment_ids: List[str] = field(default_factory=list)
    embedding_model: Optional[str] = None
    last_synced_at: Optional[str] = None
    last_full_build_at: Optional[str] = None

    def known_pr_set(self) -> Set[int]:
        return set(self.known_pr_numbers)

    def indexed_id_set(self) -> Set[str]:
        return set(self.indexed_comment_ids)


def read_sync_state(path: Path = SYNC_STATE_PATH) -> SyncState:
    if not path.exists():
        return SyncState()
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return SyncState()
    return SyncState(
        known_pr_numbers=[int(n) for n in raw.get("known_pr_numbers") or []],
        indexed_comment_ids=[str(i) for i in raw.get("indexed_comment_ids") or []],
        embedding_model=raw.get("embedding_model"),
        last_synced_at=raw.get("last_synced_at"),
        last_full_build_at=raw.get("last_full_build_at"),
    )


def write_sync_state(state: SyncState, path: Path = SYNC_STATE_PATH) -> None:
    ensure_mosaic_dirs()
    payload = asdict(state)
    # Stable ordering for readable diffs
    payload["known_pr_numbers"] = sorted(set(state.known_pr_numbers))
    payload["indexed_comment_ids"] = sorted(set(state.indexed_comment_ids))
    path.write_text(json.dumps(payload, indent=2) + "\n")


def record_full_build(
    *,
    pr_numbers: Iterable[int],
    comment_ids: Iterable[str],
    embedding_model: str,
) -> SyncState:
    now = _utcnow()
    state = SyncState(
        known_pr_numbers=sorted(set(pr_numbers)),
        indexed_comment_ids=sorted(set(comment_ids)),
        embedding_model=embedding_model,
        last_synced_at=now,
        last_full_build_at=now,
    )
    write_sync_state(state)
    return state


def record_sync_delta(
    *,
    new_pr_numbers: Iterable[int],
    new_comment_ids: Iterable[str],
    embedding_model: Optional[str] = None,
) -> SyncState:
    state = read_sync_state()
    state.known_pr_numbers = sorted(state.known_pr_set() | set(new_pr_numbers))
    state.indexed_comment_ids = sorted(state.indexed_id_set() | set(new_comment_ids))
    if embedding_model:
        state.embedding_model = embedding_model
    state.last_synced_at = _utcnow()
    write_sync_state(state)
    return state
