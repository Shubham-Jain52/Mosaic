"""Mosaic CLI — init, scrape, and build the vector index."""

from __future__ import annotations

import getpass
from typing import Dict, Optional

import typer

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
    EmbeddingSettings,
    ensure_mosaic_dirs,
    parse_repo_url,
    persist_embedding_settings,
    write_env,
)
from core.database import init_db, save_data_to_db
from core.repository import count_comments_by_type, get_comment_corpus
from pipeline.indexer import build_vector_index
from scrapers.github import GitHubAPIError, fetch_pull_requests

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
  2. mosaic scrape   Fetch all PRs and labeled comments into mosaic.db
  3. mosaic build    Configure embeddings and build the Chroma vector DB

Commands:
  init     Connect a GitHub repository (URL + PAT → .env, create DB tables)
  scrape   Paginate all PRs and comments (review, issue, review summaries)
  build    Choose local (fastembed) or API embeddings, then index into Chroma
  help     Show this overview

Tips:
  • API-only install:  pip install -e .
  • Local embeddings:  pip install -e '.[local]'   (or mosaic-cli[local])
  • Secrets live in .env; vector store / config under .mosaic/ (gitignored)
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
        help="GitHub Personal Access Token. Prompted securely if omitted.",
    ),
) -> None:
    """Connect a repository: save URL + PAT to .env and create the local DB."""
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

    pat = token
    while not pat:
        pat = getpass.getpass("GitHub Personal Access Token (input hidden): ").strip()
        if not pat:
            typer.echo("Token cannot be empty.")

    write_env(
        github_token=pat,
        repo_owner=owner,
        repo_name=name,
        repo_url=repo_url,
    )
    init_db()

    typer.secho("Saved connection settings to .env", fg=typer.colors.GREEN)
    typer.echo(f"  REPO_URL    = {repo_url}")
    typer.echo(f"  REPO_OWNER  = {owner}")
    typer.echo(f"  REPO_NAME   = {name}")
    typer.echo("  GITHUB_TOKEN = ***")
    typer.echo("\nDatabase tables are ready (mosaic.db).")
    typer.echo(
        "Tip: if mosaic.db still has old test rows, delete it and re-run "
        "`mosaic init` before the first real scrape."
    )
    typer.echo("\nNext: run `mosaic scrape` to fetch all PRs and review comments.")


@app.command("scrape")
def scrape_cmd() -> None:
    """Fetch all PRs + review comments for the connected repo and save to SQLite."""
    init_db()
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
        for label, count in sorted(by_type.items()):
            typer.echo(f"  {label}: {count}")


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


@app.command("build")
def build_cmd() -> None:
    """Configure embeddings and build the Chroma vector DB from scraped comments."""
    init_db()
    ensure_mosaic_dirs()

    counts = count_comments_by_type()
    corpus = get_comment_corpus()
    if not corpus:
        typer.secho(
            "No comments in mosaic.db. Run `mosaic scrape` first.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo("Mosaic build — embedding + vector index\n")
    typer.echo(f"Corpus ready: {len(corpus)} documents")
    if counts:
        for label, count in sorted(counts.items()):
            typer.echo(f"  {label}: {count}")
    typer.echo("")

    backend = _prompt_backend()
    if backend == "local":
        settings = _configure_local()
    else:
        settings = _configure_api()

    persist_embedding_settings(settings)
    typer.echo("\nSaved embedding settings to .env and .mosaic/config.json")
    typer.echo("Building Chroma vector index …")

    try:
        embedder = get_embedder(settings)
        result = build_vector_index(embedder=embedder, settings=settings, reset=True)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"Index build failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho("\nVector DB ready.", fg=typer.colors.GREEN)
    typer.echo(f"  backend    = {result['backend']}")
    typer.echo(f"  provider   = {result['provider']}")
    typer.echo(f"  model      = {result['model']}")
    typer.echo(f"  documents  = {result['documents']}")
    typer.echo(f"  collection = {result['collection']}")
    typer.echo(f"  chroma     = {result['chroma_path']}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
