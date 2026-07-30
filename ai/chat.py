"""BYOK OpenAI-compatible chat client for mosaic check."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from core.config import load_config

DEFAULT_CHAT_MODEL = "gpt-4o-mini"


class ChatError(RuntimeError):
    """Raised when chat configuration or API calls fail."""


@dataclass
class ChatSettings:
    api_key: str
    model: str
    api_base: Optional[str] = None


def get_chat_settings() -> ChatSettings:
    load_config()
    api_key = (
        os.getenv("CHAT_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("EMBEDDING_API_KEY")
        or ""
    ).strip()
    model = (os.getenv("CHAT_MODEL") or DEFAULT_CHAT_MODEL).strip()
    api_base = (os.getenv("CHAT_API_BASE") or "").strip() or None

    if not api_key:
        raise ChatError(
            "Chat API key is missing. Set CHAT_API_KEY (or OPENAI_API_KEY) in .env "
            "for mosaic check. Local embeddings do not cover the LLM step."
        )
    if not model:
        raise ChatError("CHAT_MODEL cannot be empty.")

    return ChatSettings(api_key=api_key, model=model, api_base=api_base)


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
