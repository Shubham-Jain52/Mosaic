"""Query the existing Chroma comment index for similar past review comments."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ai.embeddings import Embedder, get_embedder
from core.config import EmbeddingSettings, get_embedding_settings
from pipeline.indexer import _get_collection


def query_similar_comments(
    hunk_text: str,
    *,
    top_k: int = 5,
    embedder: Optional[Embedder] = None,
    settings: Optional[EmbeddingSettings] = None,
) -> List[Dict[str, Any]]:
    """
    Embed ``hunk_text`` and return the top-k nearest comment documents.

    Each result: id, text, pr_number, file_path, author, comment_type, distance.
    """
    query = (hunk_text or "").strip()
    if not query:
        return []

    k = max(1, int(top_k))
    cfg = settings or get_embedding_settings()
    worker = embedder or get_embedder(cfg)
    collection, _, _ = _get_collection(cfg, reset=False)

    if collection.count() == 0:
        return []

    vector = worker.embed_query(query)
    raw = collection.query(
        query_embeddings=[vector],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    results: List[Dict[str, Any]] = []
    for idx, doc_id in enumerate(ids):
        meta = metadatas[idx] if idx < len(metadatas) else {}
        meta = meta or {}
        pr_raw = meta.get("pr_number", "")
        try:
            pr_number = int(pr_raw) if pr_raw != "" and pr_raw is not None else None
        except (TypeError, ValueError):
            pr_number = None
        results.append(
            {
                "id": doc_id,
                "text": documents[idx] if idx < len(documents) else "",
                "pr_number": pr_number,
                "file_path": meta.get("file_path") or "",
                "author": meta.get("author") or "",
                "comment_type": meta.get("comment_type") or "",
                "pr_title": meta.get("pr_title") or "",
                "distance": distances[idx] if idx < len(distances) else None,
            }
        )
    return results
