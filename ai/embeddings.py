"""Embedding backends for Mosaic (local fastembed + API providers)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Sequence, Set

from requests import get, post

from core.config import (
    DEFAULT_LOCAL_MODEL,
    EmbeddingSettings,
    get_embedding_settings,
)

# Hub pipeline tags / tags that indicate an embedding-capable model.
_HF_EMBEDDING_PIPELINE_TAGS = {
    "feature-extraction",
    "sentence-similarity",
}
_HF_EMBEDDING_TAGS = {
    "feature-extraction",
    "sentence-similarity",
    "sentence-transformers",
    "embeddings",
}
_HF_REJECT_PIPELINE_TAGS = {
    "text-generation",
    "text2text-generation",
    "conversational",
    "fill-mask",
    "token-classification",
    "question-answering",
    "summarization",
    "translation",
    "zero-shot-classification",
    "image-classification",
    "automatic-speech-recognition",
}


class EmbeddingError(RuntimeError):
    """Raised when embedding configuration or API calls fail."""


class Embedder(ABC):
    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> List[float]:
        vectors = self.embed_documents([text])
        return vectors[0]


def ensure_local_embedder_available() -> None:
    """Require the optional local extra (fastembed)."""
    try:
        import fastembed  # noqa: F401
    except ImportError as exc:
        raise EmbeddingError(
            "Local embeddings require fastembed. Install with:\n"
            "  pip install 'mosaic-cli[local]'\n"
            "or:\n"
            "  pip install -e '.[local]'"
        ) from exc


class LocalEmbedder(Embedder):
    """On-device embeddings via fastembed (ONNX Runtime)."""

    def __init__(self, model: str = DEFAULT_LOCAL_MODEL):
        ensure_local_embedder_available()
        from fastembed import TextEmbedding

        name = (model or DEFAULT_LOCAL_MODEL).strip()
        if not name:
            raise EmbeddingError("Local embedding model name cannot be empty.")
        try:
            self._model = TextEmbedding(model_name=name)
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(
                f"Failed to load local fastembed model '{name}': {exc}"
            ) from exc
        self._model_name = name

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        # fastembed returns a generator of numpy arrays / lists
        vectors = list(self._model.embed(list(texts)))
        out: List[List[float]] = []
        for vec in vectors:
            if hasattr(vec, "tolist"):
                out.append(vec.tolist())
            else:
                out.append([float(x) for x in vec])
        return out

    def verify(self) -> None:
        self.embed_documents(["ping"])


class OpenAICompatibleEmbedder(Embedder):
    """OpenAI Embeddings API, or any OpenAI-compatible base URL."""

    def __init__(
        self,
        api_key: str,
        model: str,
        api_base: Optional[str] = None,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise EmbeddingError(
                "openai package is not installed. Run: pip install openai"
            ) from exc

        if not (model or "").strip():
            raise EmbeddingError("Embedding model name cannot be empty.")
        if not (api_key or "").strip():
            raise EmbeddingError("API key cannot be empty.")

        kwargs = {"api_key": api_key}
        if api_base:
            kwargs["base_url"] = api_base
        self._client = OpenAI(**kwargs)
        self._model = model.strip()

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self._model,
            input=list(texts),
        )
        data = sorted(response.data, key=lambda row: getattr(row, "index", 0))
        return [row.embedding for row in data]

    def verify(self) -> None:
        try:
            self.embed_documents(["ping"])
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            lowered = message.lower()
            if "401" in message or "invalid api key" in lowered or "unauthorized" in lowered:
                raise EmbeddingError(
                    "API key was rejected. Enter a valid embedding API key."
                ) from exc
            if "model" in lowered and (
                "not found" in lowered
                or "does not exist" in lowered
                or "invalid" in lowered
                or "not an embedding" in lowered
            ):
                raise EmbeddingError(
                    f"Model '{self._model}' was rejected by the provider. "
                    "Enter a valid embedding model id."
                ) from exc
            raise EmbeddingError(f"Embedding verification failed: {exc}") from exc


def verify_huggingface_model_metadata(model: str, api_key: Optional[str] = None) -> dict:
    """
    Fetch Hugging Face Hub model card metadata and ensure it looks embedding-capable.
    """
    model_id = (model or "").strip()
    if not model_id:
        raise EmbeddingError("Embedding model name cannot be empty.")

    headers = {"User-Agent": "Mosaic-CLI"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = get(
        f"https://huggingface.co/api/models/{model_id}",
        headers=headers,
        timeout=60,
    )
    if response.status_code == 401:
        raise EmbeddingError(
            "Hugging Face token was rejected while reading model metadata."
        )
    if response.status_code == 403:
        raise EmbeddingError(
            f"No access to Hugging Face model '{model_id}' (gated or private). "
            "Use a token with access, or pick a public embedding model."
        )
    if response.status_code == 404:
        raise EmbeddingError(
            f"Hugging Face model '{model_id}' was not found. Check the model id."
        )
    if response.status_code >= 400:
        raise EmbeddingError(
            f"Failed to fetch Hugging Face model metadata ({response.status_code}): "
            f"{response.text[:300]}"
        )

    meta = response.json()
    pipeline_tag = (meta.get("pipeline_tag") or "").strip().lower()
    tags: Set[str] = {str(t).lower() for t in (meta.get("tags") or [])}

    if pipeline_tag in _HF_REJECT_PIPELINE_TAGS:
        raise EmbeddingError(
            f"Hugging Face model '{model_id}' has pipeline_tag='{pipeline_tag}', "
            "which is not an embedding model. Pick a feature-extraction or "
            "sentence-similarity model."
        )

    is_embedding = (
        pipeline_tag in _HF_EMBEDDING_PIPELINE_TAGS
        or bool(tags & _HF_EMBEDDING_TAGS)
    )
    if not is_embedding:
        raise EmbeddingError(
            f"Hugging Face model '{model_id}' metadata does not look like an "
            f"embedding model (pipeline_tag={pipeline_tag or 'none'}). "
            "Expected feature-extraction or sentence-similarity."
        )
    return meta


class HuggingFaceEmbedder(Embedder):
    """Hugging Face Inference API feature-extraction (embeddings)."""

    def __init__(self, api_key: str, model: str, *, check_metadata: bool = True):
        if not (api_key or "").strip():
            raise EmbeddingError("Hugging Face token cannot be empty.")
        if not (model or "").strip():
            raise EmbeddingError("Embedding model name cannot be empty.")

        self._api_key = api_key.strip()
        self._model = model.strip()
        self._url = (
            f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self._model}"
        )
        if check_metadata:
            verify_huggingface_model_metadata(self._model, self._api_key)

    def _embed_one(self, text: str) -> List[float]:
        response = post(
            self._url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"inputs": text, "options": {"wait_for_model": True}},
            timeout=120,
        )
        if response.status_code == 401:
            raise EmbeddingError(
                "Hugging Face token was rejected. Enter a valid HF token."
            )
        if response.status_code == 404:
            raise EmbeddingError(
                f"Model '{self._model}' was not found on Hugging Face Inference API."
            )
        if response.status_code >= 400:
            raise EmbeddingError(
                f"Hugging Face embedding failed ({response.status_code}): {response.text[:300]}"
            )

        payload = response.json()
        vector = _mean_pool_hf_output(payload)
        if not vector:
            raise EmbeddingError(
                f"Model '{self._model}' did not return an embedding vector. "
                "It may not support feature-extraction inference."
            )
        return vector

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._embed_one(text) for text in texts]

    def verify(self) -> None:
        self.embed_documents(["ping"])


def _mean_pool_hf_output(payload) -> List[float]:
    """Normalize HF feature-extraction JSON into a single vector."""
    if isinstance(payload, dict) and "error" in payload:
        raise EmbeddingError(f"Hugging Face error: {payload['error']}")

    if isinstance(payload, list) and payload and isinstance(payload[0], (int, float)):
        return [float(x) for x in payload]

    if (
        isinstance(payload, list)
        and payload
        and isinstance(payload[0], list)
        and payload[0]
        and isinstance(payload[0][0], (int, float))
    ):
        width = len(payload[0])
        sums = [0.0] * width
        for token in payload:
            for i, value in enumerate(token):
                sums[i] += float(value)
        n = float(len(payload))
        return [value / n for value in sums]

    if (
        isinstance(payload, list)
        and payload
        and isinstance(payload[0], list)
        and payload[0]
        and isinstance(payload[0][0], list)
    ):
        return _mean_pool_hf_output(payload[0])

    return []


def verify_api_embedder(
    *,
    provider: str,
    api_key: str,
    model: str,
    api_base: Optional[str] = None,
) -> Embedder:
    """Construct and live-verify an API embedder (no name heuristics)."""
    provider = provider.lower().strip()
    if provider == "huggingface":
        # Metadata check first, then Inference ping.
        verify_huggingface_model_metadata(model, api_key)
        embedder = HuggingFaceEmbedder(
            api_key=api_key,
            model=model,
            check_metadata=False,
        )
        embedder.verify()
        return embedder
    if provider in {"openai", "openai_compatible", "compatible"}:
        embedder = OpenAICompatibleEmbedder(
            api_key=api_key,
            model=model,
            api_base=api_base,
        )
        embedder.verify()
        return embedder
    raise EmbeddingError(
        f"Unknown embedding provider '{provider}'. "
        "Use openai, huggingface, or openai_compatible."
    )


def get_embedder(settings: Optional[EmbeddingSettings] = None) -> Embedder:
    """Factory: build the configured embedder for index/query."""
    cfg = settings or get_embedding_settings()
    if cfg.backend == "local":
        return LocalEmbedder(model=cfg.model)
    if cfg.provider == "huggingface":
        return HuggingFaceEmbedder(
            api_key=cfg.api_key or "",
            model=cfg.model,
            check_metadata=False,
        )
    return OpenAICompatibleEmbedder(
        api_key=cfg.api_key or "",
        model=cfg.model,
        api_base=cfg.api_base,
    )
