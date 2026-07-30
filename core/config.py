"""Load and validate Mosaic configuration from the environment."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv

ENV_PATH = Path(".env")
MOSAIC_DIR = Path(".mosaic")
CHROMA_DIR = MOSAIC_DIR / "chroma"
MOSAIC_CONFIG_PATH = MOSAIC_DIR / "config.json"

# User-global Mosaic home (token shared across projects)
GLOBAL_MOSAIC_DIR = Path.home() / ".mosaic"
GLOBAL_ENV_PATH = GLOBAL_MOSAIC_DIR / ".env"
GLOBAL_TOKEN_KEY = "MOSAIC_GITHUB_TOKEN"

# fastembed-supported default (ONNX); override at `mosaic build` prompt.
DEFAULT_LOCAL_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_COLLECTION_NAME = "mosaic_comments"

_REPO_SHORTHAND = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$")


def ensure_global_mosaic_dir() -> None:
    """Create ~/.mosaic/ if missing."""
    GLOBAL_MOSAIC_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> None:
    """
    Load env vars for Mosaic.

    Order (dotenv does not override already-set process env):
      1. ~/.mosaic/.env  (global — e.g. MOSAIC_GITHUB_TOKEN)
      2. ./.env          (per-project)
    """
    load_dotenv(GLOBAL_ENV_PATH)
    load_dotenv(ENV_PATH)


def ensure_mosaic_dirs() -> None:
    """Create .mosaic/ and chroma/ directories if missing."""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def get_global_github_token() -> Optional[str]:
    """Return MOSAIC_GITHUB_TOKEN from process env or ~/.mosaic/.env, if set."""
    load_dotenv(GLOBAL_ENV_PATH)
    token = (os.getenv(GLOBAL_TOKEN_KEY) or "").strip()
    return token or None


def save_global_github_token(token: str) -> Path:
    """Persist MOSAIC_GITHUB_TOKEN to ~/.mosaic/.env. Returns the path written."""
    ensure_global_mosaic_dir()
    cleaned = (token or "").strip()
    if not cleaned:
        raise ValueError("GitHub token cannot be empty.")
    update_env({GLOBAL_TOKEN_KEY: cleaned}, env_path=GLOBAL_ENV_PATH)
    os.environ[GLOBAL_TOKEN_KEY] = cleaned
    return GLOBAL_ENV_PATH


def write_project_env(
    *,
    repo_owner: str,
    repo_name: str,
    repo_url: str,
    github_token: Optional[str] = None,
    env_path: Path = ENV_PATH,
) -> None:
    """
    Create or update per-project .env with repo identity.

    Writes GITHUB_TOKEN only when ``github_token`` is provided (legacy /
    no-global-token path). Prefer a global MOSAIC_GITHUB_TOKEN instead.
    """
    values: Dict[str, str] = {
        "REPO_OWNER": repo_owner.strip(),
        "REPO_NAME": repo_name.strip(),
        "REPO_URL": repo_url.strip(),
    }
    if github_token is not None and str(github_token).strip():
        values["GITHUB_TOKEN"] = str(github_token).strip()
    update_env(values, env_path=env_path)


def parse_repo_url(url: str) -> Tuple[str, str]:
    """
    Parse a GitHub repo reference into (owner, name).

    Accepts:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
      - owner/repo
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Repository URL cannot be empty.")

    if raw.startswith("git@"):
        match = re.match(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?/?$", raw)
        if not match:
            raise ValueError(f"Unsupported git SSH URL: {url}")
        return match.group(1), match.group(2)

    shorthand = _REPO_SHORTHAND.match(raw)
    if shorthand:
        return shorthand.group(1), shorthand.group(2)

    parsed = urlparse(raw)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("Repository must be a github.com URL or owner/repo shorthand.")

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse owner/repo from URL: {url}")

    owner, name = parts[0], parts[1]
    if name.endswith(".git"):
        name = name[:-4]
    if not owner or not name:
        raise ValueError(f"Could not parse owner/repo from URL: {url}")
    return owner, name


def get_github_token() -> str:
    """
    Resolve GitHub PAT for API calls.

    Preference: MOSAIC_GITHUB_TOKEN (global / process) → GITHUB_TOKEN (project .env).
    """
    load_config()
    token = (
        (os.getenv(GLOBAL_TOKEN_KEY) or "").strip()
        or (os.getenv("GITHUB_TOKEN") or "").strip()
    )
    if not token:
        raise RuntimeError(
            "No GitHub token found. Run `mosaic init` (saves MOSAIC_GITHUB_TOKEN "
            f"to {GLOBAL_ENV_PATH}) or set GITHUB_TOKEN in the project .env."
        )
    return token


def get_repo() -> Tuple[str, str]:
    load_config()
    owner = (os.getenv("REPO_OWNER") or "").strip()
    name = (os.getenv("REPO_NAME") or "").strip()
    if not owner or not name:
        raise RuntimeError(
            "REPO_OWNER / REPO_NAME are not set. Run `mosaic init` to connect a repository."
        )
    return owner, name


def get_github_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {get_github_token()}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Mosaic-CLI",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def update_env(values: Dict[str, str], env_path: Path = ENV_PATH) -> None:
    """Merge key/value pairs into .env (create file if needed)."""
    existing: Dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            existing[key.strip()] = value

    for key, value in values.items():
        if value is None:
            continue
        existing[key] = str(value).strip()

    lines = [f"{key}={value}" for key, value in existing.items()]
    env_path.write_text("\n".join(lines) + "\n")


def write_env(
    *,
    github_token: str,
    repo_owner: str,
    repo_name: str,
    repo_url: str,
    env_path: Path = ENV_PATH,
) -> None:
    """Create or update .env with Mosaic connection settings (legacy helper)."""
    write_project_env(
        repo_owner=repo_owner,
        repo_name=repo_name,
        repo_url=repo_url,
        github_token=github_token,
        env_path=env_path,
    )


@dataclass
class EmbeddingSettings:
    backend: str  # local | api
    provider: str  # local | openai | huggingface | openai_compatible
    model: str
    model_path: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    chroma_path: str = str(CHROMA_DIR)
    collection_name: str = DEFAULT_COLLECTION_NAME


def get_embedding_settings() -> EmbeddingSettings:
    load_config()
    backend = (os.getenv("EMBEDDING_BACKEND") or "").strip().lower()
    provider = (os.getenv("EMBEDDING_PROVIDER") or "").strip().lower()
    model = (os.getenv("EMBEDDING_MODEL") or "").strip()
    model_path = (os.getenv("EMBEDDING_MODEL_PATH") or "").strip() or None
    api_base = (os.getenv("EMBEDDING_API_BASE") or "").strip() or None

    if not backend or not model:
        raise RuntimeError(
            "Embedding settings are not configured. Run `mosaic build` first."
        )

    if backend == "local":
        provider = provider or "local"
        api_key = None
    else:
        provider = provider or "openai"
        if provider == "huggingface":
            api_key = (os.getenv("HF_TOKEN") or os.getenv("EMBEDDING_API_KEY") or "").strip()
        else:
            api_key = (
                os.getenv("EMBEDDING_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or ""
            ).strip()
        if not api_key:
            raise RuntimeError(
                "Embedding API key is missing. Run `mosaic build` to configure it."
            )

    file_cfg = read_mosaic_config()
    return EmbeddingSettings(
        backend=backend,
        provider=provider,
        model=model,
        model_path=model_path,
        api_key=api_key,
        api_base=api_base,
        chroma_path=file_cfg.get("chroma_path", str(CHROMA_DIR)),
        collection_name=file_cfg.get("collection_name", DEFAULT_COLLECTION_NAME),
    )


def read_mosaic_config() -> Dict[str, Any]:
    if not MOSAIC_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(MOSAIC_CONFIG_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def write_mosaic_config(data: Dict[str, Any]) -> None:
    ensure_mosaic_dirs()
    payload = dict(data)
    payload["built_at"] = datetime.now(timezone.utc).isoformat()
    MOSAIC_CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def persist_embedding_settings(settings: EmbeddingSettings) -> None:
    """Write embedding settings to .env and .mosaic/config.json."""
    ensure_mosaic_dirs()
    env_values: Dict[str, str] = {
        "EMBEDDING_BACKEND": settings.backend,
        "EMBEDDING_PROVIDER": settings.provider,
        "EMBEDDING_MODEL": settings.model,
        "EMBEDDING_MODEL_PATH": settings.model_path or "",
        "EMBEDDING_API_BASE": settings.api_base or "",
    }
    if settings.backend == "api" and settings.api_key:
        if settings.provider == "huggingface":
            env_values["HF_TOKEN"] = settings.api_key
            env_values["EMBEDDING_API_KEY"] = settings.api_key
        elif settings.provider == "openai":
            env_values["OPENAI_API_KEY"] = settings.api_key
            env_values["EMBEDDING_API_KEY"] = settings.api_key
        else:
            env_values["EMBEDDING_API_KEY"] = settings.api_key

    update_env(env_values)
    write_mosaic_config(
        {
            "embedding_backend": settings.backend,
            "embedding_provider": settings.provider,
            "embedding_model": settings.model,
            "embedding_model_path": settings.model_path,
            "embedding_api_base": settings.api_base,
            "collection_name": settings.collection_name,
            "chroma_path": settings.chroma_path,
        }
    )
