"""Mosaic CLI — init, build (ingest + index), sync, and check."""

from __future__ import annotations

import getpass
import sys
from typing import Dict, List, Optional, Set

import typer

from ai.chat import (
    DEFAULT_CHAT_MODEL,
    GROQ_API_BASE,
    OPENAI_API_BASE,
    OPENROUTER_API_BASE,
    ChatError,
    ChatSettings,
    ResolvedChatProvider,
    default_chat_model_for_provider,
    format_api_base_for_display,
    peek_chat_settings,
    resolve_chat_provider,
    sample_models_for_provider,
    verify_chat_settings,
)
from ai.embeddings import (
    EmbeddingError,
    LocalEmbedder,
    ensure_local_embedder_available,
    get_embedder,
    verify_api_embedder,
)
from core.config import (
    DEFAULT_LOCAL_MODEL,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    ENV_PATH,
    EmbeddingSettings,
    GLOBAL_ENV_PATH,
    ensure_mosaic_dirs,
    get_embedding_settings,
    get_global_github_token,
    get_repo,
    parse_repo_url,
    persist_embedding_settings,
    save_chat_settings,
    save_global_github_token,
    write_project_env,
)
from core.database import init_db, save_data_to_db
from core.git_diff import GitDiffError, get_working_diff, resolve_diff_base
from core.gitignore_util import ensure_mosaic_gitignore
from core.repository import (
    comment_ids_for_prs,
    count_comments_by_type,
    get_comment_corpus,
    get_pr_numbers,
)
from core.sync_state import (
    read_sync_state,
    record_full_build,
    record_sync_delta,
)
from pipeline.check_runner import run_check
from pipeline.indexer import build_vector_index, index_corpus_delta
from scrapers.github import (
    GitHubAPIError,
    fetch_pull_request,
    fetch_pull_requests,
    list_pull_request_numbers,
)

app = typer.Typer(
    name="mosaic",
    help="Mosaic — build a review-comment dataset from a GitHub repository.",
    no_args_is_help=True,
)


@app.command("help")
def help_cmd() -> None:
    """Show what Mosaic is and which commands are available."""
    typer.echo(
        """
Mosaic
------
CLI tool that connects to a GitHub repo, scrapes PR review / conversation
comments into SQLite, then builds a vector index for RAG over that feedback.

Typical flow:
  1. mosaic init     Connect a repo + GitHub PAT (.env)
  2. mosaic build    Full scrape + configure embeddings + vector index
  3. mosaic sync     Fetch only new PRs and vectorize the delta (optional)
  4. mosaic check    Advisory review of your changes vs main (BYOK chat)

Commands:
  init     Connect a GitHub repository (URL → .env; PAT saved globally once)
  build    Full ingest + embedder setup + Chroma index (first-time pipeline)
  sync     Delta: PRs not yet in SQLite → save → vectorize → ready
  check    Diff vs main (auto) → graded, cited feedback from past reviews
  help     Show this overview

Notes:
  • V1 sync only picks up new PR numbers (not new comments on existing PRs).
  • GitHub PAT is stored once in ~/.mosaic/.env (MOSAIC_GITHUB_TOKEN).
  • check prompts for OpenAI-compatible CHAT_API_KEY (+ provider/model) if missing.
  • API-only install:  pip install -e .
  • Local embeddings:  pip install -e '.[local]'   (or mosaic-cli[local])
  • Project .env holds REPO_*; Chroma + sync state under .mosaic/ (gitignored)
  • Per-command flags:  mosaic <command> --help
""".strip()
    )


@app.command("init")
def init_cmd(
    repo: Optional[str] = typer.Option(
        None,
        "--repo",
        "-r",
        help="GitHub repo URL or owner/repo. Prompted if omitted.",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub Personal Access Token. Uses global token if set; else prompted.",
    ),
) -> None:
    """Connect a repository: save URL to .env and create the local DB."""
    typer.echo("Mosaic init — connect a GitHub repository\n")

    raw_repo = repo
    while not raw_repo:
        raw_repo = typer.prompt("GitHub repository URL (or owner/repo)")

    try:
        owner, name = parse_repo_url(raw_repo)
    except ValueError as exc:
        typer.secho(f"Invalid repository: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    repo_url = f"https://github.com/{owner}/{name}"

    global_token = get_global_github_token()
    project_token: Optional[str] = None
    token_source = "global"

    if token:
        pat = token.strip()
        if not pat:
            typer.secho("Token cannot be empty.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        if not global_token:
            if typer.confirm(
                f"Save this token to {GLOBAL_ENV_PATH} for all Mosaic projects?",
                default=True,
            ):
                save_global_github_token(pat)
                typer.echo(f"Saved MOSAIC_GITHUB_TOKEN to {GLOBAL_ENV_PATH}")
                token_source = "global"
            else:
                project_token = pat
                token_source = "project"
        else:
            # Explicit --token while global exists: keep using global unless they
            # want this project-only override.
            if typer.confirm(
                "A global Mosaic GitHub token already exists. "
                "Use the token you just passed for this project only?",
                default=False,
            ):
                project_token = pat
                token_source = "project"
            else:
                token_source = "global"
    elif global_token:
        typer.echo(f"Using GitHub token from {GLOBAL_ENV_PATH} (MOSAIC_GITHUB_TOKEN)")
        token_source = "global"
    else:
        pat = ""
        while not pat:
            pat = getpass.getpass("GitHub Personal Access Token (input hidden): ").strip()
            if not pat:
                typer.echo("Token cannot be empty.")
        if typer.confirm(
            f"Save this token to {GLOBAL_ENV_PATH} for all Mosaic projects?",
            default=True,
        ):
            save_global_github_token(pat)
            typer.echo(f"Saved MOSAIC_GITHUB_TOKEN to {GLOBAL_ENV_PATH}")
            token_source = "global"
        else:
            project_token = pat
            token_source = "project"

    write_project_env(
        repo_owner=owner,
        repo_name=name,
        repo_url=repo_url,
        github_token=project_token,
    )
    added_ignores = ensure_mosaic_gitignore()
    init_db()

    typer.secho("Saved connection settings to .env", fg=typer.colors.GREEN)
    typer.echo(f"  REPO_URL    = {repo_url}")
    typer.echo(f"  REPO_OWNER  = {owner}")
    typer.echo(f"  REPO_NAME   = {name}")
    if token_source == "global":
        typer.echo(f"  GitHub token = *** (global: {GLOBAL_ENV_PATH})")
    else:
        typer.echo("  GITHUB_TOKEN = *** (project .env)")
    if added_ignores:
        typer.secho(
            "Updated .gitignore with: " + ", ".join(added_ignores),
            fg=typer.colors.GREEN,
        )
    else:
        typer.echo("Mosaic paths already present in .gitignore.")
    typer.echo("\nDatabase tables are ready (mosaic.db).")
    typer.echo(
        "Tip: if mosaic.db still has old test rows, delete it and re-run "
        "`mosaic init` before the first real build."
    )
    typer.echo("\nNext: run `mosaic build` to scrape, configure embeddings, and index.")


def _prompt_backend() -> str:
    typer.echo("Embedding backend:")
    typer.echo("  1) local  — on-device via fastembed (requires mosaic-cli[local])")
    typer.echo("  2) api    — OpenAI, Hugging Face, or OpenAI-compatible endpoint")
    while True:
        choice = typer.prompt("Choose backend", default="2").strip().lower()
        if choice in {"1", "local", "l"}:
            return "local"
        if choice in {"2", "api", "a"}:
            return "api"
        typer.echo("Enter 1/local or 2/api.")


def _prompt_api_provider() -> str:
    typer.echo("\nAPI provider:")
    typer.echo("  1) openai             — OpenAI embeddings")
    typer.echo("  2) huggingface        — Hugging Face Inference API")
    typer.echo("  3) openai_compatible  — any OpenAI-compatible base URL")
    while True:
        choice = typer.prompt("Choose provider", default="1").strip().lower()
        if choice in {"1", "openai", "o"}:
            return "openai"
        if choice in {"2", "huggingface", "hf", "h"}:
            return "huggingface"
        if choice in {"3", "openai_compatible", "compatible", "c"}:
            return "openai_compatible"
        typer.echo("Enter 1/openai, 2/huggingface, or 3/openai_compatible.")


def _configure_local() -> EmbeddingSettings:
    try:
        ensure_local_embedder_available()
    except EmbeddingError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    model = typer.prompt(
        "Local fastembed model id",
        default=DEFAULT_LOCAL_MODEL,
    ).strip()
    if not model:
        typer.secho("Model id cannot be empty.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\nLoading local model '{model}' (weights use the fastembed cache) …")
    try:
        embedder = LocalEmbedder(model=model)
        embedder.verify()
    except EmbeddingError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho("Local embedder ready.", fg=typer.colors.GREEN)
    return EmbeddingSettings(
        backend="local",
        provider="local",
        model=model,
        model_path=None,
    )


def _configure_api() -> EmbeddingSettings:
    provider = _prompt_api_provider()
    default_model = (
        DEFAULT_OPENAI_EMBEDDING_MODEL
        if provider != "huggingface"
        else "sentence-transformers/all-MiniLM-L6-v2"
    )
    api_base: Optional[str] = None
    if provider == "openai_compatible":
        api_base = typer.prompt("API base URL (OpenAI-compatible)").strip()
        if not api_base:
            typer.secho("API base URL is required.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    key_label = {
        "openai": "OpenAI API key",
        "huggingface": "Hugging Face token",
        "openai_compatible": "API key",
    }[provider]

    while True:
        api_key = getpass.getpass(f"{key_label} (input hidden): ").strip()
        if api_key:
            break
        typer.echo("API key cannot be empty.")

    while True:
        model = typer.prompt("Embedding model id", default=default_model).strip()
        try:
            typer.echo("Verifying provider credentials + embedding model …")
            verify_api_embedder(
                provider=provider,
                api_key=api_key,
                model=model,
                api_base=api_base,
            )
            break
        except EmbeddingError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            if "api key" in str(exc).lower() or "token was rejected" in str(exc).lower():
                api_key = getpass.getpass(f"Re-enter {key_label} (input hidden): ").strip()
                if not api_key:
                    raise typer.Exit(code=1)
            typer.echo("Enter a model id that the provider accepts for embeddings.")

    typer.secho("API embedding configuration verified.", fg=typer.colors.GREEN)
    return EmbeddingSettings(
        backend="api",
        provider=provider,
        model=model,
        api_key=api_key,
        api_base=api_base,
    )


def _require_repo_config() -> None:
    try:
        get_repo()
    except RuntimeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


def _print_comment_breakdown(by_type: Dict[str, int]) -> None:
    for label, count in sorted(by_type.items()):
        typer.echo(f"  {label}: {count}")


@app.command("build")
def build_cmd() -> None:
    """Full scrape + configure embeddings + build the Chroma vector index."""
    init_db()
    ensure_mosaic_dirs()
    _require_repo_config()

    typer.echo("Mosaic build — scrape + embeddings + vector index\n")

    backend = _prompt_backend()
    if backend == "local":
        settings = _configure_local()
    else:
        settings = _configure_api()
    persist_embedding_settings(settings)
    typer.echo("\nSaved embedding settings to .env and .mosaic/config.json")

    typer.echo("\nFetching all pull requests and comments from GitHub …")
    try:
        pull_requests = fetch_pull_requests()
    except (RuntimeError, GitHubAPIError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    save_data_to_db(pull_requests)
    total_comments = sum(len(pr.comments) for pr in pull_requests)
    by_type: Dict[str, int] = {}
    for pr in pull_requests:
        for comment in pr.comments:
            by_type[comment.comment_type] = by_type.get(comment.comment_type, 0) + 1

    typer.secho(
        f"Saved {len(pull_requests)} PRs and {total_comments} comments to mosaic.db",
        fg=typer.colors.GREEN,
    )
    if by_type:
        _print_comment_breakdown(by_type)

    corpus = get_comment_corpus()
    if not corpus:
        typer.secho(
            "Ingestion finished but there are no comments to vectorize. "
            "The connected repo may have no review/conversation comments yet.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"\nBuilding Chroma vector index ({len(corpus)} documents) …")
    try:
        embedder = get_embedder(settings)
        result = build_vector_index(embedder=embedder, settings=settings, reset=True)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"Index build failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    record_full_build(
        pr_numbers=get_pr_numbers(),
        comment_ids=result["comment_ids"],
        embedding_model=settings.model,
    )

    typer.secho("\nVector DB ready.", fg=typer.colors.GREEN)
    typer.echo(f"  backend    = {result['backend']}")
    typer.echo(f"  provider   = {result['provider']}")
    typer.echo(f"  model      = {result['model']}")
    typer.echo(f"  documents  = {result['documents']}")
    typer.echo(f"  collection = {result['collection']}")
    typer.echo(f"  chroma     = {result['chroma_path']}")
    typer.secho("\nMosaic is ready for your questions.", fg=typer.colors.GREEN)
    typer.echo("Later: run `mosaic sync` to pull only new PRs, then ask (coming soon).")


@app.command("sync")
def sync_cmd() -> None:
    """Fetch PRs not yet in SQLite, vectorize their comments, update sync state."""
    init_db()
    ensure_mosaic_dirs()
    _require_repo_config()

    try:
        settings = get_embedding_settings()
    except RuntimeError as exc:
        typer.secho(
            f"{exc}\nRun `mosaic build` first to configure embeddings and create the index.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    state = read_sync_state()
    existing: Set[int] = state.known_pr_set() | set(get_pr_numbers())

    typer.echo("Mosaic sync — checking GitHub for PRs not yet in mosaic.db …")
    try:
        remote_numbers = set(list_pull_request_numbers())
    except (RuntimeError, GitHubAPIError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    missing: List[int] = sorted(remote_numbers - existing)
    if not missing:
        typer.secho("Everything up to date.", fg=typer.colors.GREEN)
        if state.last_synced_at:
            typer.echo(f"  last_synced_at = {state.last_synced_at}")
        typer.echo("Mosaic is ready for your questions.")
        return

    typer.echo(f"Found {len(missing)} new PR(s): {missing[:20]}{'…' if len(missing) > 20 else ''}")
    owner, repo = get_repo()
    fetched = []
    for number in missing:
        typer.echo(f"  Fetching PR #{number} …")
        try:
            fetched.append(fetch_pull_request(number, owner, repo))
        except GitHubAPIError as exc:
            typer.secho(f"  Skipping PR #{number}: {exc}", fg=typer.colors.YELLOW)

    if not fetched:
        typer.secho("No PRs could be fetched.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    save_data_to_db(fetched)
    new_pr_numbers = [pr.number for pr in fetched]
    new_comment_ids = comment_ids_for_prs(new_pr_numbers)
    total_comments = sum(len(pr.comments) for pr in fetched)
    typer.secho(
        f"Saved {len(fetched)} PRs and {total_comments} comments to mosaic.db",
        fg=typer.colors.GREEN,
    )

    if not new_comment_ids:
        record_sync_delta(
            new_pr_numbers=new_pr_numbers,
            new_comment_ids=[],
            embedding_model=settings.model,
        )
        typer.echo("New PRs had no indexable comments; sync state updated.")
        typer.secho("Mosaic is ready for your questions.", fg=typer.colors.GREEN)
        return

    typer.echo(f"Vectorizing {len(new_comment_ids)} new comment(s) …")
    try:
        embedder = get_embedder(settings)
        result = index_corpus_delta(
            new_comment_ids,
            embedder=embedder,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"Delta index failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    record_sync_delta(
        new_pr_numbers=new_pr_numbers,
        new_comment_ids=result["comment_ids"],
        embedding_model=settings.model,
    )

    typer.secho(
        f"Indexed {result['documents']} new document(s) into {result['collection']}.",
        fg=typer.colors.GREEN,
    )
    typer.secho("Mosaic is ready for your questions.", fg=typer.colors.GREEN)


def _format_feedback_block(result) -> None:
    if result.messages:
        for msg in result.messages:
            typer.echo(msg)

    if not result.feedback:
        if not result.messages:
            typer.echo("No findings.")
        return

    order = {"blocking": 0, "suggestion": 1, "nit": 2}
    sorted_items = sorted(
        result.feedback,
        key=lambda f: (order.get(f.severity, 9), f.file_path, f.issue),
    )
    typer.echo("")
    typer.echo("Findings")
    typer.echo("--------")
    for item in sorted_items:
        cites = ", ".join(f"#{n}" for n in item.cited_prs) or "(none)"
        loc = item.file_path
        if item.line_hint:
            loc = f"{loc}:{item.line_hint}"
        typer.echo(f"[{item.severity.upper()}] {loc}")
        typer.echo(f"  {item.issue}")
        typer.echo(f"  cited: {cites}")
        typer.echo("")


def _log_chat_setup(message: str) -> None:
    """Credential-setup progress (never include API keys)."""
    typer.echo(f"[mosaic] {message}")


def _prompt_chat_provider(
    default_raw: str = "1",
) -> ResolvedChatProvider:
    """
    Prompt for chat provider by number, alias name, or full custom URL.

    Typing ``Groq`` / ``openai`` / ``OpenRouter`` resolves to the known base URL.
    """
    typer.echo("\nChat provider / API base:")
    typer.echo(f"  1) OpenAI      — {OPENAI_API_BASE}  (or leave blank)")
    typer.echo(f"  2) Groq        — {GROQ_API_BASE}")
    typer.echo(f"  3) OpenRouter  — {OPENROUTER_API_BASE}")
    typer.echo("  4) Custom URL  — any OpenAI-compatible /v1 host")
    typer.echo("Type a number, provider name (e.g. Groq), or paste a full URL.")

    while True:
        raw = typer.prompt(
            "Choose provider",
            default=default_raw,
            show_default=True,
        ).strip()
        try:
            resolved = resolve_chat_provider(raw)
        except ChatError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            continue

        if resolved.provider_id == "custom" and not resolved.api_base:
            custom_url = typer.prompt(
                "Custom OpenAI-compatible API base URL",
                default="",
                show_default=False,
            ).strip()
            if not custom_url:
                typer.echo("Custom URL cannot be empty.")
                continue
            try:
                resolved = resolve_chat_provider(custom_url)
            except ChatError as exc:
                typer.secho(str(exc), fg=typer.colors.RED, err=True)
                continue
            if not resolved.api_base:
                typer.echo("Enter a full https://… URL for a custom host.")
                continue
            resolved = ResolvedChatProvider(
                provider_id="custom",
                api_base=resolved.api_base,
                display_name="Custom",
                from_alias=False,
            )

        base_display = format_api_base_for_display(resolved.api_base)
        if resolved.from_alias:
            _log_chat_setup(
                f"Resolved provider {resolved.display_name} → {base_display}"
            )
        else:
            _log_chat_setup(f"Using API base {base_display}")
        return resolved


def _prompt_chat_model(
    provider: ResolvedChatProvider,
    previous_model: str = "",
) -> str:
    """Prompt for a chat model with numbered samples for known providers."""
    samples = sample_models_for_provider(provider.provider_id)
    model_default = previous_model or default_chat_model_for_provider(
        provider.provider_id, provider.api_base
    )

    if not samples:
        model = typer.prompt(
            "Chat model id",
            default=model_default or DEFAULT_CHAT_MODEL,
        ).strip()
        if not model:
            typer.secho("Chat model cannot be empty.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        _log_chat_setup(f"Using chat model {model}")
        return model

    typer.echo(f"\nSample models for {provider.display_name}:")
    for idx, name in enumerate(samples, start=1):
        marker = "  (recommended)" if idx == 1 else ""
        typer.echo(f"  {idx}) {name}{marker}")
    other_n = len(samples) + 1
    typer.echo(f"  {other_n}) Other / custom model id")
    typer.echo("Type a number, or paste any model id the provider accepts.")

    default_choice = "1"
    if previous_model:
        if previous_model in samples:
            default_choice = str(samples.index(previous_model) + 1)
        else:
            default_choice = previous_model

    while True:
        raw = typer.prompt(
            "Choose model",
            default=default_choice,
            show_default=True,
        ).strip()
        if not raw:
            typer.echo("Model cannot be empty.")
            continue

        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(samples):
                model = samples[n - 1]
                _log_chat_setup(f"Using chat model {model}")
                return model
            if n == other_n:
                custom = typer.prompt(
                    "Custom model id",
                    default=previous_model or model_default,
                ).strip()
                if not custom:
                    typer.echo("Model cannot be empty.")
                    continue
                _log_chat_setup(f"Using chat model {custom}")
                return custom
            typer.echo(f"Enter 1–{other_n}, or a model id.")
            continue

        # Free-text model id (or alias-like paste of a known sample name).
        model = raw
        _log_chat_setup(f"Using chat model {model}")
        return model


def _ensure_chat_credentials() -> None:
    """
    Ensure a chat API key is available for mosaic check.

    If CHAT_API_KEY / OPENAI_API_KEY / EMBEDDING_API_KEY is already set
    (global ~/.mosaic/.env or project .env), do nothing. Otherwise prompt for
    an OpenAI-compatible key + provider/base + model, verify with a cheap
    ping, and offer to save globally by default.
    """
    existing = peek_chat_settings()
    if existing is not None:
        return

    typer.echo("Chat API key is required for mosaic check (BYOK).")
    typer.echo(
        "Use any OpenAI-compatible provider key (OpenAI, Groq, OpenRouter, "
        "Together, local gateway, …) — not OpenAI-only."
    )
    typer.echo("Any key format is accepted (no sk- prefix required).")

    api_key = ""
    while not api_key:
        api_key = getpass.getpass(
            "OpenAI-compatible chat API key (input hidden): "
        ).strip()
        if not api_key:
            typer.echo("API key cannot be empty.")

    provider = _prompt_chat_provider()
    api_base = provider.api_base
    model = _prompt_chat_model(provider)

    while True:
        settings = ChatSettings(api_key=api_key, model=model, api_base=api_base)
        base_display = format_api_base_for_display(api_base)
        try:
            _log_chat_setup(
                f"Verifying chat credentials (base={base_display}, model={model}) …"
            )
            verify_chat_settings(settings)
            break
        except ChatError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            _log_chat_setup(
                f"Verification failed for base={base_display} model={model} "
                "(API key not printed)."
            )
            typer.echo(
                "Check key, provider/base, and model together — non-OpenAI keys "
                "need the matching API base (e.g. Groq + a Groq model)."
            )
            api_key = getpass.getpass(
                "Re-enter OpenAI-compatible chat API key (input hidden): "
            ).strip()
            if not api_key:
                raise typer.Exit(code=1) from exc
            # Prefer the last resolved provider number when re-prompting.
            default_raw = {
                "openai": "1",
                "groq": "2",
                "openrouter": "3",
                "custom": "4",
            }.get(provider.provider_id, "1")
            if provider.provider_id == "custom" and api_base:
                default_raw = api_base
            provider = _prompt_chat_provider(default_raw=default_raw)
            api_base = provider.api_base
            model = _prompt_chat_model(provider, previous_model=model)

    _log_chat_setup("Chat credentials verified.")
    typer.secho("Chat credentials verified.", fg=typer.colors.GREEN)

    if typer.confirm(
        f"Save chat settings to {GLOBAL_ENV_PATH} for all Mosaic projects?",
        default=True,
    ):
        path = save_chat_settings(
            api_key=api_key,
            model=model,
            api_base=api_base,
            env_path=GLOBAL_ENV_PATH,
        )
        saved = "CHAT_API_KEY / CHAT_MODEL"
        if api_base:
            saved += " / CHAT_API_BASE"
        typer.echo(f"Saved {saved} to {path}")
    else:
        path = save_chat_settings(
            api_key=api_key,
            model=model,
            api_base=api_base,
            env_path=ENV_PATH,
        )
        saved = "CHAT_API_KEY / CHAT_MODEL"
        if api_base:
            saved += " / CHAT_API_BASE"
        typer.echo(f"Saved {saved} to {path} (project only)")


@app.command("check")
def check_cmd(
    top_k: int = typer.Option(
        5,
        "--top-k",
        help="Number of similar past comments to retrieve per hunk.",
    ),
    base: Optional[str] = typer.Option(
        None,
        "--base",
        help="Git ref to diff against (default: origin/main, main, …).",
    ),
    use_stdin: bool = typer.Option(
        False,
        "--stdin",
        help="Read a unified diff from stdin instead of running git diff.",
    ),
) -> None:
    """
    Advisory check: compare your working tree to main and flag patterns
    from past PR review comments (BYOK chat). Always exits 0 on success.
    """
    # Resolve diff text: --stdin always; non-empty pipe; else auto git diff
    if use_stdin:
        diff_text = sys.stdin.read()
        typer.echo("Using diff from stdin")
    elif not sys.stdin.isatty():
        piped_text = sys.stdin.read()
        if piped_text.strip():
            diff_text = piped_text
            typer.echo("Using diff from stdin")
        else:
            try:
                resolved = resolve_diff_base(base)
                diff_text = get_working_diff(resolved)
            except GitDiffError as exc:
                typer.secho(str(exc), fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1) from exc
            typer.echo(f"Diffing against {resolved}")
    else:
        try:
            resolved = resolve_diff_base(base)
            diff_text = get_working_diff(resolved)
        except GitDiffError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"Diffing against {resolved}")

    try:
        get_embedding_settings()
    except RuntimeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    try:
        _ensure_chat_credentials()
    except ChatError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    try:
        result = run_check(diff_text, top_k=top_k)
    except (ChatError, EmbeddingError, RuntimeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if result.trivial:
        typer.echo("no meaningful changes detected")
        raise typer.Exit(code=0)

    _format_feedback_block(result)
    typer.echo(f"LLM calls: {result.llm_call_count} (hunks: {result.hunk_count})")
    raise typer.Exit(code=0)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
