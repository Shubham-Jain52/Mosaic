"""BYOK OpenAI-compatible chat client for mosaic check."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from core.config import load_config

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_GROQ_CHAT_MODEL = "openai/gpt-oss-20b"
GROQ_API_BASE = "https://api.groq.com/openai/v1"
OPENAI_API_BASE = "https://api.openai.com/v1"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"

# Canonical provider ids → base URL (OpenAI may be stored as blank / None).
PROVIDER_BASES: Dict[str, str] = {
    "openai": OPENAI_API_BASE,
    "groq": GROQ_API_BASE,
    "openrouter": OPENROUTER_API_BASE,
}

PROVIDER_ALIASES: Dict[str, str] = {
    "openai": "openai",
    "oai": "openai",
    "1": "openai",
    "groq": "groq",
    "2": "groq",
    "openrouter": "openrouter",
    "open-router": "openrouter",
    "or": "openrouter",
    "3": "openrouter",
    "custom": "custom",
    "url": "custom",
    "4": "custom",
}

PROVIDER_SAMPLE_MODELS: Dict[str, List[str]] = {
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "groq": [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
    ],
    "openrouter": [
        "openai/gpt-4o-mini",
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
    ],
    "custom": [],
}

PROVIDER_DISPLAY_NAMES: Dict[str, str] = {
    "openai": "OpenAI",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "custom": "Custom",
}


class ChatError(RuntimeError):
    """Raised when chat configuration or API calls fail."""


@dataclass
class ChatSettings:
    api_key: str
    model: str
    api_base: Optional[str] = None


@dataclass(frozen=True)
class ResolvedChatProvider:
    """Result of resolving a provider name or API base URL."""

    provider_id: str
    api_base: Optional[str]
    display_name: str
    from_alias: bool = False


def sample_models_for_provider(provider_id: str) -> List[str]:
    """Return sample chat model ids for a known provider (empty for custom)."""
    return list(PROVIDER_SAMPLE_MODELS.get((provider_id or "").strip().lower(), []))


def default_chat_model_for_base(api_base: Optional[str]) -> str:
    """Pick a sensible default CHAT_MODEL for a known OpenAI-compatible host."""
    base = (api_base or "").strip().lower()
    if "groq.com" in base:
        return DEFAULT_GROQ_CHAT_MODEL
    if "openrouter.ai" in base:
        samples = PROVIDER_SAMPLE_MODELS["openrouter"]
        return samples[0] if samples else DEFAULT_CHAT_MODEL
    return DEFAULT_CHAT_MODEL


def default_chat_model_for_provider(provider_id: str, api_base: Optional[str] = None) -> str:
    """Default model for a resolved provider id (falls back to base URL heuristics)."""
    samples = sample_models_for_provider(provider_id)
    if samples:
        return samples[0]
    return default_chat_model_for_base(api_base)


def _looks_like_url(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _provider_id_for_base(api_base: Optional[str]) -> str:
    base = (api_base or "").strip().lower()
    if not base or "api.openai.com" in base:
        return "openai"
    if "groq.com" in base:
        return "groq"
    if "openrouter.ai" in base:
        return "openrouter"
    return "custom"


def resolve_chat_provider(raw: str) -> ResolvedChatProvider:
    """
    Resolve a provider name, numbered choice, or full URL to an API base.

    Known aliases (case-insensitive): openai, groq, openrouter (and short forms).
    Full http(s) URLs pass through as custom. Blank → OpenAI default (no base).
    """
    text = (raw or "").strip()
    if not text:
        return ResolvedChatProvider(
            provider_id="openai",
            api_base=None,
            display_name=PROVIDER_DISPLAY_NAMES["openai"],
            from_alias=True,
        )

    if _looks_like_url(text):
        provider_id = _provider_id_for_base(text)
        # Strip trailing slash for consistency with known constants.
        api_base = text.rstrip("/")
        return ResolvedChatProvider(
            provider_id=provider_id,
            api_base=api_base,
            display_name=PROVIDER_DISPLAY_NAMES.get(provider_id, "Custom"),
            from_alias=False,
        )

    # Normalize "Open Router" / "OpenAI" / numbered choices.
    key = "".join(text.lower().split())
    provider_id = PROVIDER_ALIASES.get(key)
    if provider_id is None:
        raise ChatError(
            f"Unknown chat provider {text!r}. Choose OpenAI, Groq, OpenRouter, "
            "Custom, or paste a full https://…/v1 URL."
        )

    if provider_id == "custom":
        return ResolvedChatProvider(
            provider_id="custom",
            api_base=None,
            display_name=PROVIDER_DISPLAY_NAMES["custom"],
            from_alias=True,
        )

    if provider_id == "openai":
        # Match prior BYOK behavior: blank base = OpenAI SDK default.
        return ResolvedChatProvider(
            provider_id="openai",
            api_base=None,
            display_name=PROVIDER_DISPLAY_NAMES["openai"],
            from_alias=True,
        )

    return ResolvedChatProvider(
        provider_id=provider_id,
        api_base=PROVIDER_BASES[provider_id],
        display_name=PROVIDER_DISPLAY_NAMES[provider_id],
        from_alias=True,
    )


def format_api_base_for_display(api_base: Optional[str]) -> str:
    """Human-readable base URL for logs / errors (never includes the API key)."""
    return (api_base or "").strip() or OPENAI_API_BASE


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


def mask_api_key(api_key: str) -> str:
    """Return a display-safe masked key (never the full secret)."""
    text = (api_key or "").strip()
    if not text:
        return "(not set)"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}…{text[-4:]}"


def get_chat_settings() -> ChatSettings:
    settings = peek_chat_settings()
    if settings is None:
        raise ChatError(
            "Chat API key is missing. Run `mosaic settings` or `mosaic check` "
            "to enter one, or set CHAT_API_KEY (or OPENAI_API_KEY) in "
            "~/.mosaic/.env or project .env. "
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
    base_display = format_api_base_for_display(settings.api_base)
    model = settings.model.strip()
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        raise ChatError(
            f"Chat API key verification failed for base {base_display!r} "
            f"model {model!r}: {exc}"
        ) from exc


class OpenAICompatibleChat:
    """Chat completions via OpenAI or any OpenAI-compatible base URL."""

    def __init__(
        self,
        settings: Optional[ChatSettings] = None,
        *,
        rate_limit_delay_s: float = 0.2,
        max_retries: int = 3,
    ):
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
        self._rate_limit_delay_s = max(0.0, float(rate_limit_delay_s))
        self._max_retries = max(1, int(max_retries))
        self._last_call_at: Optional[float] = None

    def _wait_for_rate_limit(self) -> None:
        if self._rate_limit_delay_s <= 0:
            return
        import time

        if self._last_call_at is None:
            return
        elapsed = time.monotonic() - self._last_call_at
        remaining = self._rate_limit_delay_s - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _is_rate_limited(exc: BaseException) -> bool:
        text = str(exc).lower()
        if "429" in text or "rate limit" in text or "too many requests" in text:
            return True
        status = getattr(exc, "status_code", None)
        if status == 429:
            return True
        response = getattr(exc, "response", None)
        if response is not None and getattr(response, "status_code", None) == 429:
            return True
        return False

    def complete(self, messages: Sequence[Dict[str, str]]) -> str:
        if not messages:
            raise ChatError("Chat messages cannot be empty.")

        import time

        last_exc: Optional[BaseException] = None
        for attempt in range(self._max_retries):
            self._wait_for_rate_limit()
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=list(messages),
                    temperature=0,
                )
                self._last_call_at = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self._last_call_at = time.monotonic()
                if self._is_rate_limited(exc) and attempt + 1 < self._max_retries:
                    # Exponential backoff: 1s, 2s, 4s…
                    time.sleep(2**attempt)
                    continue
                raise ChatError(f"Chat completion failed: {exc}") from exc

            choices = getattr(response, "choices", None) or []
            if not choices:
                raise ChatError("Chat completion returned no choices.")
            message = choices[0].message
            content = getattr(message, "content", None)
            if not content or not str(content).strip():
                raise ChatError("Chat completion returned empty content.")
            return str(content).strip()

        raise ChatError(f"Chat completion failed: {last_exc}")
