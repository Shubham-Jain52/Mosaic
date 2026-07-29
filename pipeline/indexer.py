"""Build a Chroma vector index from the SQLite comment corpus."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ai.embeddings import Embedder, get_embedder
from core.config import (
    CHROMA_DIR,
    DEFAULT_COLLECTION_NAME,
    EmbeddingSettings,
    ensure_mosaic_dirs,
    get_embedding_settings,
)
from core.repository import get_comment_corpus


def _chroma_safe_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    for key in ("pr_number", "comment_type", "author", "file_path", "pr_title", "review_state"):
        value = item.get(key)
        if value is None:
            meta[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            meta[key] = value
        else:
            meta[key] = str(value)
    return meta


def _get_collection(cfg: EmbeddingSettings, *, reset: bool):
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "chromadb is not installed. Run: pip install chromadb"
        ) from exc

    chroma_path = Path(cfg.chroma_path or CHROMA_DIR)
    chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection_name = cfg.collection_name or DEFAULT_COLLECTION_NAME
    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:  # noqa: BLE001 - collection may not exist yet
            pass
    collection = client.get_or_create_collection(name=collection_name)
    return collection, collection_name, chroma_path


def _upsert_corpus_batch(
    collection,
    corpus: Sequence[Dict[str, Any]],
    worker: Embedder,
    batch_size: int,
) -> int:
    total = 0
    for start in range(0, len(corpus), batch_size):
        batch = list(corpus[start : start + batch_size])
        ids = [item["id"] for item in batch]
        documents = [item["text"] for item in batch]
        metadatas = [_chroma_safe_metadata(item) for item in batch]
        embeddings = worker.embed_documents(documents)
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        total += len(batch)
    return total


def build_vector_index(
    *,
    embedder: Optional[Embedder] = None,
    settings: Optional[EmbeddingSettings] = None,
    batch_size: int = 64,
    reset: bool = True,
) -> Dict[str, Any]:
    """
    Embed the full comment corpus and upsert into a persistent Chroma collection.

    One corpus comment == one vector document (no extra chunking in this phase).
    """
    ensure_mosaic_dirs()
    cfg = settings or get_embedding_settings()
    worker = embedder or get_embedder(cfg)

    corpus = get_comment_corpus()
    if not corpus:
        raise RuntimeError(
            "No comments found in mosaic.db after ingestion. "
            "Nothing to vectorize — the connected repo may have no review/conversation comments."
        )

    collection, collection_name, chroma_path = _get_collection(cfg, reset=reset)
    total = _upsert_corpus_batch(collection, corpus, worker, batch_size)

    return {
        "documents": total,
        "comment_ids": [item["id"] for item in corpus],
        "collection": collection_name,
        "chroma_path": str(chroma_path),
        "backend": cfg.backend,
        "provider": cfg.provider,
        "model": cfg.model,
    }


def index_corpus_delta(
    comment_ids: List[str],
    *,
    embedder: Optional[Embedder] = None,
    settings: Optional[EmbeddingSettings] = None,
    batch_size: int = 64,
) -> Dict[str, Any]:
    """
    Embed and upsert only the given composite comment ids (no collection reset).
    """
    ensure_mosaic_dirs()
    cfg = settings or get_embedding_settings()
    worker = embedder or get_embedder(cfg)

    unique_ids = sorted(set(comment_ids))
    if not unique_ids:
        return {
            "documents": 0,
            "comment_ids": [],
            "collection": cfg.collection_name or DEFAULT_COLLECTION_NAME,
            "chroma_path": str(cfg.chroma_path or CHROMA_DIR),
            "backend": cfg.backend,
            "provider": cfg.provider,
            "model": cfg.model,
        }

    corpus = get_comment_corpus(comment_ids=unique_ids)
    if not corpus:
        return {
            "documents": 0,
            "comment_ids": [],
            "collection": cfg.collection_name or DEFAULT_COLLECTION_NAME,
            "chroma_path": str(cfg.chroma_path or CHROMA_DIR),
            "backend": cfg.backend,
            "provider": cfg.provider,
            "model": cfg.model,
        }

    collection, collection_name, chroma_path = _get_collection(cfg, reset=False)
    total = _upsert_corpus_batch(collection, corpus, worker, batch_size)

    return {
        "documents": total,
        "comment_ids": [item["id"] for item in corpus],
        "collection": collection_name,
        "chroma_path": str(chroma_path),
        "backend": cfg.backend,
        "provider": cfg.provider,
        "model": cfg.model,
    }
