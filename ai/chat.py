"""BYOK OpenAI-compatible chat client for mosaic check."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from core.config import load_config

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"
GROQ_API_BASE = "https://api.groq.com/openai/v1"
OPENAI_API_BASE = "https://api.openai.com/v1"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


class ChatError(RuntimeError):
    """Raised when chat configuration or API calls fail."""


@dataclass
class ChatSettings:
    api_key: str
    model: str
    api_base: Optional[str] = None


def default_chat_model_for_base(api_base: Optional[str]) -> str:
    """Pick a sensible default CHAT_MODEL for a known OpenAI-compatible host."""
    base = (api_base or "").strip().lower()
    if "groq.com" in base:
        return DEFAULT_GROQ_CHAT_MODEL
    return DEFAULT_CHAT_MODEL


def _lookup_chat_api_key() -> str:
    """Resolve chat key from process env / loaded dotenv (global then project)."""
    return (
        os.getenv("CHAT_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("EMBEDDING_API_KEY")
        or ""
    ).strip()


def peek_chat_settings() -> Optional[ChatSettings]:
    """Return chat settings if an API key is configured; otherwise None."""
    load_config()
    api_key = _lookup_chat_api_key()
    if not api_key:
        return None
    model = (os.getenv("CHAT_MODEL") or DEFAULT_CHAT_MODEL).strip()
    if not model:
        return None
    api_base = (os.getenv("CHAT_API_BASE") or "").strip() or None
    return ChatSettings(api_key=api_key, model=model, api_base=api_base)


def get_chat_settings() -> ChatSettings:
    settings = peek_chat_settings()
    if settings is None:
        raise ChatError(
            "Chat API key is missing. Run `mosaic check` to enter one, or set "
            "CHAT_API_KEY (or OPENAI_API_KEY) in ~/.mosaic/.env or project .env. "
            "Local embeddings do not cover the LLM step."
        )
    return settings


def verify_chat_settings(settings: ChatSettings) -> None:
    """Cheap chat completion ping to validate key / model / base URL."""
    if not (settings.api_key or "").strip():
        raise ChatError("Chat API key cannot be empty.")
    if not (settings.model or "").strip():
        raise ChatError("CHAT_MODEL cannot be empty.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ChatError(
            "openai package is not installed. Run: pip install openai"
        ) from exc

    kwargs: Dict[str, Any] = {"api_key": settings.api_key.strip()}
    if settings.api_base:
        kwargs["base_url"] = settings.api_base
    client = OpenAI(**kwargs)
    try:
        client.chat.completions.create(
            model=settings.model.strip(),
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        raise ChatError(f"Chat API key verification failed: {exc}") from exc


class OpenAICompatibleChat:
    """Chat completions via OpenAI or any OpenAI-compatible base URL."""

    def __init__(self, settings: Optional[ChatSettings] = None):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ChatError(
                "openai package is not installed. Run: pip install openai"
            ) from exc

        cfg = settings or get_chat_settings()
        kwargs: Dict[str, Any] = {"api_key": cfg.api_key}
        if cfg.api_base:
            kwargs["base_url"] = cfg.api_base
        self._client = OpenAI(**kwargs)
        self._model = cfg.model

    def complete(self, messages: Sequence[Dict[str, str]]) -> str:
        if not messages:
            raise ChatError("Chat messages cannot be empty.")
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=list(messages),
                temperature=0,
            )
        except Exception as exc:  # noqa: BLE001
            raise ChatError(f"Chat completion failed: {exc}") from exc

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ChatError("Chat completion returned no choices.")
        message = choices[0].message
        content = getattr(message, "content", None)
        if not content or not str(content).strip():
            raise ChatError("Chat completion returned empty content.")
        return str(content).strip()
